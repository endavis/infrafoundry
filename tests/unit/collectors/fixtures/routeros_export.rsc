# 2000-01-01 00:00:00 by RouterOS 7.0
# model = CRS-example
/interface bridge add name=bridge1 vlan-filtering=yes
/ip address add address=192.0.2.2/24 interface=bridge1
/interface wifi security add name=sec1 passphrase=CANARY-WIFI-0001
