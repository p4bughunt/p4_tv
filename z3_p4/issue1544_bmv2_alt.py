from p4z3_expressions import *


def p4_program_0(z3_reg):

    import v1model
    z3_reg = v1model.register(z3_reg)

    z3_args = [
        ('dstAddr', BitVecSort(48)),
        ('srcAddr', BitVecSort(48)),
        ('etherType', BitVecSort(16))]

    z3_reg.register_z3_type("ethernet_t", Header, z3_args)

    z3_args = [('ethernet', z3_reg.types["ethernet_t"])]
    z3_reg.register_z3_type("headers", Struct, z3_args)

    z3_args = []
    z3_reg.register_z3_type("metadata", Struct, z3_args)

    def p():
        pass

    def vrfy():
        pass

    def update():
        pass

    def egress():
        pass

    def deparser():
        pass

    z3_args = [('hdr', z3_reg.types["headers"]), ('meta', z3_reg.types["metadata"]),
               ('standard_metadata', z3_reg.types["standard_metadata_t"])]
    z3_reg.register_z3_type("inouts", P4State, z3_args)
    ingress_args = z3_reg.instance("inouts")

    def ingress(p4_vars):

        my_drop = P4Action()
        my_drop.add_parameter("smeta", z3_reg.types["standard_metadata_t"])

        set_port = P4Action()
        set_port.add_parameter("output_port", BitVecSort(9))

        lval = "standard_metadata.egress_spec"
        rval = "output_port"
        assign = AssignmentStatement(lval, rval)
        set_port.add_stmt(assign)

        mac_da_0 = P4Table("mac_da_0")

        mac_da_0.add_action("set_port", set_port)

        args = ["standard_metadata"]
        mac_da_0.add_action("my_drop", my_drop)

        args = ["standard_metadata"]
        mac_da_0.add_default(my_drop, args)

        table_key = "hdr.ethernet.dstAddr"
        mac_da_0.add_match(table_key)

        def BLOCK():
            block = BlockStatement()
            block.add(mac_da_0.apply())

            def BLOCK():
                block = BlockStatement()

                rval = P4Slice("hdr.ethernet.srcAddr", 15, 0)
                lval = "x_0"
                decl = P4Declaration(lval, rval)
                block.add(decl)

                rval = False
                lval = "hasReturned"
                decl = P4Declaration(lval, rval)
                block.add(decl)

                rval = BitVec("retval", 16)
                lval = "retval"
                decl = P4Declaration(lval)
                block.add(decl)

                if_block = IfStatement()

                condition = P4gt("x_0", BitVecVal(5, 16))
                if_block.add_condition(condition)

                rval = True
                lval = "hasReturned"
                assign = AssignmentStatement(lval, rval)
                if_block.add_then_stmt(assign)

                rval = P4add("x_0", BitVecVal(65535, 16))
                lval = "retval"
                assign = AssignmentStatement(lval, rval)
                if_block.add_then_stmt(assign)

                rval = True
                lval = "hasReturned"
                assign = AssignmentStatement(lval, rval)
                if_block.add_else_stmt(assign)

                rval = "x_0"
                lval = "retval"
                assign = AssignmentStatement(lval, rval)
                if_block.add_else_stmt(assign)
                block.add(if_block)

                rval = "retval"
                lval = "tmp"
                assign = AssignmentStatement(lval, rval)
                block.add(assign)
                return block
            block.add(BLOCK())

            rval = "tmp"
            lval = "hdr.ethernet.srcAddr"
            assign = SliceAssignment(
                lval, rval, 15, 0)
            block.add(assign)
            return block

        return BLOCK().eval(p4_vars)

    return ((p,), (vrfy,), (ingress, ingress_args), (egress,), (update,), (deparser,))


def p4_program_1(z3_reg):

    import v1model
    z3_reg = v1model.register(z3_reg)

    z3_args = [
        ('dstAddr', BitVecSort(48)),
        ('srcAddr', BitVecSort(48)),
        ('etherType', BitVecSort(16))]

    z3_reg.register_z3_type("ethernet_t", Header, z3_args)

    z3_args = [('ethernet', z3_reg.types["ethernet_t"])]
    z3_reg.register_z3_type("headers", Struct, z3_args)

    z3_args = []
    z3_reg.register_z3_type("metadata", Struct, z3_args)

    def p():
        pass

    def vrfy():
        pass

    def update():
        pass

    def egress():
        pass

    def deparser():
        pass

    z3_args = [('hdr', z3_reg.types["headers"]), ('meta', z3_reg.types["metadata"]),
               ('standard_metadata', z3_reg.types["standard_metadata_t"])]
    z3_reg.register_z3_type("inouts", P4State, z3_args)
    ingress_args = z3_reg.instance("inouts")

    def ingress(p4_vars):

        my_drop = P4Action()
        my_drop.add_parameter("smeta", z3_reg.types["standard_metadata_t"])
        p4_vars.set_or_add_var("my_drop", my_drop)

        set_port = P4Action()
        set_port.add_parameter("output_port", BitVecSort(9))

        lval = "standard_metadata.egress_spec"
        rval = "output_port"
        assign = AssignmentStatement(lval, rval)
        set_port.add_stmt(assign)
        p4_vars.set_or_add_var("set_port", set_port)

        mac_da_0 = P4Table("mac_da_0")

        mac_da_0.add_action(p4_vars, MethodCallExpr("set_port"))

        args = ["standard_metadata"]
        mac_da_0.add_action(p4_vars, MethodCallExpr("my_drop", *args))

        args = ["standard_metadata"]
        mac_da_0.add_default(p4_vars, MethodCallExpr("my_drop", *args))

        table_key = "hdr.ethernet.dstAddr"
        mac_da_0.add_match(table_key)
        p4_vars.set_or_add_var("mac_da_0", mac_da_0)

        def BLOCK():
            block = BlockStatement()
            block.add(MethodCallExpr("mac_da_0.apply"))

            if_block = IfStatement()

            condition = P4gt(P4Slice("hdr.ethernet.srcAddr", 15, 0),
                             BitVecVal(5, 16))
            if_block.add_condition(condition)

            rval = P4add(P4Slice("hdr.ethernet.srcAddr", 15, 0),
                         BitVecVal(65535, 16))
            lval = "retval"
            assign = AssignmentStatement(lval, rval)
            if_block.add_then_stmt(assign)

            rval = P4Slice("hdr.ethernet.srcAddr", 15, 0)
            lval = "retval"
            assign = AssignmentStatement(lval, rval)
            if_block.add_else_stmt(assign)

            block.add(if_block)

            rval = P4or(P4and("hdr.ethernet.srcAddr", P4inv(BitVecVal(
                0xffff, 48))), P4and(P4rshift(P4Cast("retval", 48), 0), BitVecVal(0xffff, 48)))
            lval = "hdr.ethernet.srcAddr"
            assign = AssignmentStatement(lval, rval)
            block.add(assign)
            return block

        return BLOCK().eval(p4_vars)

    return ((p,), (vrfy,), (ingress, ingress_args), (egress,), (update,), (deparser,))


def z3_check():
    s = Solver()

    p4_ctrl_0, p4_ctrl_0_args = p4_program_1(Z3Reg())[2]
    p4_ctrl_1, p4_ctrl_1_args = p4_program_1(Z3Reg())[2]

    print("PROGRAM 1")
    print(p4_ctrl_0(p4_ctrl_0_args))
    print("PROGRAM 2")
    print(p4_ctrl_1(p4_ctrl_1_args))
    tv_equiv = simplify(p4_ctrl_0(p4_ctrl_0_args) !=
                        p4_ctrl_1(p4_ctrl_1_args))
    s.add(tv_equiv)
    print(tv_equiv)
    print (s.sexpr())
    ret = s.check()
    if ret == sat:
        print (ret)
        print (s.model())
        return os.EX_PROTOCOL
    else:
        print (ret)
        return os.EX_OK


if __name__ == '__main__':
    z3_check()
