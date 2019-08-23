error {
    IPv4HeaderTooShort,
    IPv4IncorrectVersion,
    IPv4ChecksumError
}
#include <core.p4>
#include <v1model.p4>
typedef bit<32> IPv4Address;
header ethernet_t {
    bit<48> dstAddr;
    bit<48> srcAddr;
    bit<16> etherType;
}
header ipv4_t {
    bit<4>      version;
    bit<4>      ihl;
    bit<8>      diffserv;
    bit<16>     totalLen;
    bit<16>     identification;
    bit<3>      flags;
    bit<13>     fragOffset;
    bit<8>      ttl;
    bit<8>      protocol;
    bit<16>     hdrChecksum;
    IPv4Address srcAddr;
    IPv4Address dstAddr;
    varbit<320> options;
}
header tcp_t {
    bit<16> srcPort;
    bit<16> dstPort;
    bit<32> seqNo;
    bit<32> ackNo;
    bit<4>  dataOffset;
    bit<3>  res;
    bit<3>  ecn;
    bit<6>  ctrl;
    bit<16> window;
    bit<16> checksum;
    bit<16> urgentPtr;
}
header IPv4_up_to_ihl_only_h {
    bit<4> version;
    bit<4> ihl;
}
struct headers {
    ethernet_t ethernet;
    ipv4_t     ipv4;
    tcp_t      tcp;
}
struct mystruct1_t {
    bit<4> a;
    bit<4> b;
}
struct metadata {
    mystruct1_t mystruct1;
    bit<16>     hash1;
}
parser parserI(packet_in pkt, out headers hdr, inout metadata meta, inout standard_metadata_t stdmeta) {
    IPv4_up_to_ihl_only_h tmp_4;
    bit<9> tmp_5;
    bit<9> tmp_6;
    bit<9> tmp_7;
    bit<32> tmp_8;
    state start {
        pkt.extract<ethernet_t>(hdr.ethernet);
        transition select(hdr.ethernet.etherType) {
            16w0x800: parse_ipv4;
            default: accept;
        }
    }
    state parse_ipv4 {
        tmp_4 = pkt.lookahead<IPv4_up_to_ihl_only_h>();
        tmp_5 = (bit<9>)tmp_4.ihl << 2;
        tmp_6 = tmp_5 + 9w492;
        tmp_7 = tmp_6 << 3;
        tmp_8 = (bit<32>)tmp_7;
        pkt.extract<ipv4_t>(hdr.ipv4, tmp_8);
        verify(hdr.ipv4.version == 4w4, error.IPv4IncorrectVersion);
        verify(hdr.ipv4.ihl >= 4w5, error.IPv4HeaderTooShort);
        transition select(hdr.ipv4.protocol) {
            8w6: parse_tcp;
            default: accept;
        }
    }
    state parse_tcp {
        pkt.extract<tcp_t>(hdr.tcp);
        transition accept;
    }
}
control cIngress(inout headers hdr, inout metadata meta, inout standard_metadata_t stdmeta) {
    @name("foo1") action foo1(IPv4Address dstAddr) {
        hdr.ipv4.dstAddr = dstAddr;
    }
    @name("foo2") action foo2(IPv4Address srcAddr) {
        hdr.ipv4.srcAddr = srcAddr;
    }
    @name("t0") table t0 {
        key = {
            hdr.tcp.dstPort: exact @name("hdr.tcp.dstPort") ;
        }
        actions = {
            foo1();
            foo2();
            @defaultonly NoAction();
        }
        size = 8;
        default_action = NoAction();
    }
    @name("t1") table t1 {
        key = {
            hdr.tcp.dstPort: exact @name("hdr.tcp.dstPort") ;
        }
        actions = {
            foo1();
            foo2();
            @defaultonly NoAction();
        }
        size = 8;
        default_action = NoAction();
    }
    @name("t2") table t2 {
        actions = {
            foo1();
            foo2();
            @defaultonly NoAction();
        }
        key = {
            hdr.tcp.srcPort: exact @name("hdr.tcp.srcPort") ;
            meta.hash1     : selector @name("meta.hash1") ;
        }
        size = 16;
        default_action = NoAction();
    }
    apply {
        t0.apply();
        t1.apply();
        meta.hash1 = hdr.ipv4.dstAddr[15:0];
        t2.apply();
    }
}
control cEgress(inout headers hdr, inout metadata meta, inout standard_metadata_t stdmeta) {
    apply {
    }
}
control vc(inout headers hdr, inout metadata meta) {
    apply {
    }
}
control uc(inout headers hdr, inout metadata meta) {
    apply {
    }
}
control DeparserI(packet_out packet, in headers hdr) {
    apply {
        packet.emit<ethernet_t>(hdr.ethernet);
        packet.emit<ipv4_t>(hdr.ipv4);
        packet.emit<tcp_t>(hdr.tcp);
    }
}
V1Switch<headers, metadata>(parserI(), vc(), cIngress(), cEgress(), uc(), DeparserI()) main;