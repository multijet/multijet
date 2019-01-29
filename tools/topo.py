import docker
import os, shutil, signal, time, sys, urllib2, shutil, urllib
import utils
import grequests
from multiprocessing.pool import ThreadPool
import redis

client = docker.from_env()


class Router:
    def __init__(self, id):
        self.id = id
        self.neighbors = []
        self.port_offset = 0


class RocketFuel:
    def __init__(self, filename, host_nodes=None):
        if host_nodes is None:
            self.host_nodes = []
        else:
            self.host_nodes = host_nodes
        self.routers = {}
        self.links = []
        self.containers = {}
        self.redis_clients = []
        self.pool = ThreadPool()

        with open(filename, 'r') as f:
            for line in f:
                arr = line.split()
                self.routers[arr[0]] = Router(arr[0])

            f.seek(0)

            # generate links
            for line in f:
                arr = line.split('->')
                arr = arr[1].split('=')
                nei_str = arr[0].replace(' ', '')
                nei_ids = nei_str[1:-1].split('><')
                t = line.split()
                router = self.routers[t[0]]
                for nei in nei_ids:
                    router.neighbors.append(self.routers[nei])

            for r in self.routers.values():
                for n in r.neighbors:
                    exists = False
                    for l in self.links:
                        if n in l and r in l:
                            exists = True
                    if not exists:
                        self.links.append([r, n])

            print len(self.links)

    def start_container(self, r):
        print 'starting ' + r.id
        container = client.containers.run('snlab/dovs-quagga', detach=True, name=r.id, privileged=True, tty=True,
                                          hostname=r.id,
                                          volumes={os.getcwd() + '/configs/' + r.id: {'bind': '/etc/quagga'},
                                                   os.getcwd() + '/tools/bootstrap': {'bind': '/bootstrap'},
                                                   os.getcwd() + '/tools/fpm': {'bind': '/fpm'},
                                                   os.getcwd() + '/multijet': {'bind': '/multijet'}},
                                          command='/bootstrap/start.sh')
        self.containers[r.id] = container

        return 'ok'

    def start(self):

        # generate ospf config file
        self.gen_config()

        self.pool.map(self.start_container, self.routers.values())
        self.pool.close()
        self.pool.join()
        print 'create end'

        # for r in self.routers.values():
        time.sleep(3)  # wait for redis start

        # for r in self.routers.values():
        #     print 'start multijet for ' + r.id
        #     c = self.containers[r.id]
        #     c.exec_run('ryu-manager /multijet/multijet.py', detach=True)

        print 'setup links'
        i = 0
        j = 0
        for l in self.links:
            src_pid = client.containers.get(l[0].id).attrs['State']['Pid']
            dst_pid = client.containers.get(l[1].id).attrs['State']['Pid']
            cmd = 'nsenter -t ' + str(src_pid) + ' -n ip link add e' + str(
                l[0].port_offset) + ' type veth peer name e' + str(l[
                                                                       1].port_offset) + ' netns ' + str(dst_pid)
            os.system(cmd)

            print 'setup links for ' + str(l[0].id)
            # set peer 1
            utils.nsenter_run(src_pid, 'ovs-vsctl add-port s e' + str(l[0].port_offset))
            utils.nsenter_run(src_pid, 'ovs-vsctl add-port s i' + str(l[0].port_offset) + ' -- set interface i' + str(
                l[0].port_offset) + ' type=internal')

            ip = '1.' + str(j) + '.' + str(i) + '.1/24'
            utils.nsenter_run(src_pid, 'ifconfig i' + str(l[0].port_offset) + ' ' + ip)
            utils.nsenter_run(src_pid, 'ifconfig e' + str(l[0].port_offset) + ' 0.0.0.0')

            print 'setup links for ' + str(l[1].id)
            # set peer 2
            utils.nsenter_run(dst_pid, 'ovs-vsctl add-port s e' + str(l[1].port_offset))
            utils.nsenter_run(dst_pid,
                              'ovs-vsctl add-port s i' + str(l[1].port_offset) + ' -- set interface i' + str(
                                  l[1].port_offset) + ' type=internal')
            ip = '1.' + str(j) + '.' + str(i) + '.2/24'
            utils.nsenter_run(dst_pid, 'ifconfig i' + str(l[1].port_offset) + ' ' + ip)
            utils.nsenter_run(dst_pid, 'ifconfig e' + str(l[1].port_offset) + ' 0.0.0.0')

            l[0].port_offset = l[0].port_offset + 1
            l[1].port_offset = l[1].port_offset + 1

            if i == 254:
                j = 1
                i = 0
            i = i + 1

        # configure ospf rules
        for id in self.routers:
            print 'configure ospf rule of ' + id
            c = self.containers[id]
            c.exec_run('/bootstrap/ospf.py', detach=True)

        # for r in self.routers.values():
        #     print 'start ospf for ' + r.id
        #     c = self.containers[r.id]
        #     c.exec_run('zebra -d -f /etc/quagga/zebra.conf --fpm_format protobuf')
        #     c.exec_run('ospfd -d -f /etc/quagga/ospfd.conf')

        for r in self.routers.values():
            print 'start fpm for ' + r.id
            c = self.containers[r.id]
            c.exec_run('python /fpm/main.py &', detach=True)

        print 'finished'

    def stop(self, sig=None, frame=None):
        print 'cleaning containers...'

        for name in self.containers:
            client.containers.get(name).remove(force=True)

        exit(0)

    def gen_config(self):
        if os.path.exists('configs'):
            shutil.rmtree('configs')
        for r in self.routers.values():
            utils.mkdir_p('configs/' + r.id)
            with open('configs/' + r.id + '/zebra.conf', 'a') as f:
                f.write('hostname Router\npassword zebra\nenable password zebra')

            with open('configs/' + r.id + '/ospfd.conf', 'a') as f:
                f.write('hostname ospfd\npassword zebra\nlog stdout\nrouter ospf\n')

        i = 0
        j = 0
        for l in self.links:
            k = 1
            for r in l:
                ip = '1.' + str(j) + '.' + str(i) + '.' + str(k) + '/24'
                with open('configs/' + r.id + '/ospfd.conf', 'a') as f:
                    f.write(' network ' + ip + ' area 0\n')

                k = k + 1
            if i == 254:
                j = 1
                i = 0
            i = i + 1

        # for r in self.routers.values():
        #     if r.id in self.host_nodes:
        #         ip = '10.0.0.0/24'
        #         with open('configs/' + r.id + '/ospfd.conf', 'a') as f:
        #             f.write(' network ' + ip + ' area 0\n')

    def start_cli(self):
        for c in self.containers:
            ip = str(client.containers.get(c).attrs['NetworkSettings']['Networks']['bridge']['IPAddress'])
            self.redis_clients.append(redis.Redis(host=ip, port=6379, db=0))

        while True:
            cmd = raw_input('multijet> ')
            if cmd == 'init':
                for r in self.redis_clients:
                    r.publish('cmd', 'init')
            elif cmd == 'addcp':
                for r in self.redis_clients:
                    r.publish('cmd', 'addcp')
            elif cmd == 'verify':
                for r in self.redis_clients:
                    r.publish('cmd', 'verify')
            elif cmd == 'compose':
                reach = raw_input('reach: ')
                for r in self.redis_clients:
                    r.publish('cmd', 'compose:' + reach)
            elif cmd[:8] == 'linkdown':
                for r in self.redis_clients:
                    r.publish('cmd', cmd)
            elif cmd[:8] == 'linkup':
                for r in self.redis_clients:
                    r.publish('cmd', cmd)


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print 'please specify topo file and nodes with host'
        exit()
    topofile = sys.argv[1]
    # host_nodes = sys.argv[2].split(',')
    topo = RocketFuel(topofile)
    signal.signal(signal.SIGINT, topo.stop)
    topo.start()
    topo.start_cli()
