control c(inout bit<32> x) {
    bit<32> arg_1;
    @name("c.a") action a() {
        arg_1 = 32w10;
        x = arg_1;
    }
    @name("c.t") table t_0 {
        actions = {
            a();
        }
        default_action = a();
    }
    apply {
        t_0.apply();
    }
}
control proto(inout bit<32> arg);
package top(proto p);
top(c()) main;