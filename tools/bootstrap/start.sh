#!/bin/bash
service openvswitch-switch start
ovs-vsctl add-br s
ovs-vsctl set-controller s tcp:127.0.0.1:6633
ovs-vsctl set-fail-mode s secure
zebra -d -f /etc/quagga/zebra.conf --fpm_format protobuf
sleep 1
ospfd -d -f /etc/quagga/ospfd.conf
redis-server &
sleep 3
ryu-manager /multijet/multijet.py &
bash