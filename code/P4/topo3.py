#!/usr/bin/env python3

from mininet.net import Mininet
from mininet.topo import Topo
from mininet.log import setLogLevel, info
from mininet.cli import CLI
from mininet.link import TCLink

from p4_mininet import P4Switch, P4Host

import argparse
from time import sleep
import os
import subprocess

_THIS_DIR = os.path.dirname(os.path.realpath(__file__))
_THRIFT_BASE_PORT = 9090

parser = argparse.ArgumentParser(description='Mininet demo')
parser.add_argument('--behavioral_exe', help='Path to behavioral executable',
                    type=str, action="store", required=False)
parser.add_argument('--json', help='Path to JSON config file',
                    type=str, action="store", required=False)
parser.add_argument('--cli', help='Path to BM CLI',
                    type=str, action="store", required=False)
parser.add_argument('--size', help='UDP packet size',
                    type=str, action="store", required=False)

args = parser.parse_args()

# Hardcoded fallback (overwrite parsed args if not provided)
args.json = args.json or "P4Flow.json"
args.behavioral_exe = args.behavioral_exe or "simple_switch"
args.cli = args.cli or "simple_switch_CLI"

class MyTopo(Topo):
    def __init__(self, sw_path, json_path, nb_hosts, nb_switches, links, **opts):
        super(MyTopo, self).__init__(**opts)

        for i in range(nb_switches):
            self.addSwitch(f's{i+1}',
                           sw_path=sw_path,
                           json_path=json_path,
                           thrift_port=_THRIFT_BASE_PORT + i,
                           log_console=False,
                           pcap_dump=False,
                           device_id=i)

        for h in range(nb_hosts):
            host_ip = f"10.0.{h+1}.{h+1}/24"
            host_mac = f'00:00:00:00:{h+1:02x}:{h+1:02x}'
            self.addHost(f'h{h+1}', ip=host_ip, mac=host_mac)

        for a, b in links:
            self.addLink(a, b)

def read_topo():
    nb_hosts = 0
    nb_switches = 0
    links = []
    with open("topo.txt", "r") as f:
        line = f.readline().strip()
        w, nb_switches = line.split()
        assert w == "switches"
        line = f.readline().strip()
        w, nb_hosts = line.split()
        assert w == "hosts"
        for line in f:
            line = line.strip()
            if not line:
                continue
            a, b = line.split()
            links.append((a, b))
    return int(nb_hosts), int(nb_switches), links

def main():
    nb_hosts, nb_switches, links = read_topo()

    topo = MyTopo(args.behavioral_exe,
                  args.json,
                  nb_hosts, nb_switches, links)

    net = Mininet(topo=topo,
                  host=P4Host,
                  switch=P4Switch,
                  link=TCLink,
                  controller=None)
    net.start()

    for host_name in topo.hosts():
        h = net.get(host_name)
        h_iface = list(h.intfs.values())[0]
        link = h_iface.link

        sw_iface = link.intf1 if link.intf1 != h_iface else link.intf2
        host_id = int(host_name[1:])
        sw_ip = f'10.0.{host_id}.254'

        h.defaultIntf().rename(f'{host_name}-eth0')
        h.cmd(f'arp -i {h_iface.name} -s {sw_ip} {sw_iface.mac}')
        h.cmd(f'ethtool --offload {h_iface.name} rx off tx off')
        h.cmd(f'ip route add {sw_ip} dev {h_iface.name}')
        h.cmd("sysctl -w net.ipv6.conf.all.disable_ipv6=1")
        h.cmd("sysctl -w net.ipv6.conf.default.disable_ipv6=1")
        h.cmd("sysctl -w net.ipv6.conf.lo.disable_ipv6=1")
        h.cmd("iptables -I OUTPUT -p icmp --icmp-type destination-unreachable -j DROP")
        h.setDefaultRoute(f"via {sw_ip}")

    sleep(1)

    for i in range(nb_switches):
        s = net.get(f's{i+1}')
        print("##################################")
        print(f"Switch (s{i+1})")
        print(s.cmd('ifconfig'))
        print(f"MAC Address:\t{s.MAC()}")
        print(f"IP Address:\t{s.IP()}")
        print("##################################")

        cmd = [args.cli, "--json", args.json, "--thrift-port", str(_THRIFT_BASE_PORT + i)]
        cli_input = f"s{i+1}-commands.txt"

        if os.path.exists(cli_input):
            with open(cli_input, "r") as f:
                print(" ".join(cmd))
                try:
                    output = subprocess.check_output(cmd, stdin=f, text=True)
                    print(output)
                except subprocess.CalledProcessError as e:
                    print(e)
                    print(e.output)

    sleep(1)
    print("Ready!")
    CLI(net)
    net.stop()

if __name__ == '__main__':
    setLogLevel('info')
    main()
