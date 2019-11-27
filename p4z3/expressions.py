from copy import deepcopy
from collections import OrderedDict
import operator as op
import z3

from p4z3.base import *


def resolve_expr(p4_vars, expr_chain, expr) -> z3.SortRef:
    # Resolves to z3 and z3p4 expressions, bools and int are also okay
    # resolve potential string references first
    log.debug("Resolving %s", expr)
    if isinstance(expr, str):
        val = p4_vars.resolve_reference(expr)
        if val is None:
            raise RuntimeError(f"Value {expr} could not be found!")
    else:
        val = expr
    if isinstance(val, (z3.ExprRef, int)):
        # These are z3 types and can be returned
        # Unfortunately int is part of it because z3 is very inconsistent
        # about var handling...
        return val
    if isinstance(val, P4Z3Class):
        # We got a P4 type, recurse...
        return step(p4_vars, [val] + expr_chain)
    if isinstance(val, P4ComplexType):
        # If we get a whole class return the complex z3 type
        return val
    raise TypeError(f"Value of type {type(val)} cannot be resolved!")


def resolve_action(action_expr):
    # TODO Fix this roundabout way of getting a P4 Action, super annoying...
    if isinstance(action_expr, MethodCallExpr):
        action_name = action_expr.expr
        action_args = action_expr.args
    elif isinstance(action_expr, str):
        action_name = action_expr
        action_args = []
    else:
        raise TypeError(
            f"Expected a method call, got {type(action_name)}!")
    return action_name, action_args


def get_type(p4_vars, expr_chain, expr):
    ''' Return the type of an expression, Resolve, if needed'''
    arg_expr = resolve_expr(p4_vars, expr_chain, expr)
    if isinstance(arg_expr, P4ComplexType):
        arg_type = arg_expr.const.sort()
    else:
        arg_type = arg_expr.sort()
    return arg_type


def z3_implies(p4_vars, expr_chain, cond, then_expr):
    no_match = step(p4_vars, expr_chain)
    return z3.If(cond, then_expr, no_match)


def check_bool(expr):
    if isinstance(expr, z3.BoolRef):
        # Convert boolean variables to a bit vector representation
        # TODO: Make all bools a bitvector of size 1
        expr = z3.If(expr, z3.BitVecVal(1, 1), z3.BitVecVal(0, 1))
    return expr


def check_enum(expr):
    if isinstance(expr, Enum):
        expr = expr.const
    return expr


def align_bitvecs(bitvec1, bitvec2, p4_vars, expr_chain):
    if isinstance(bitvec1, z3.BitVecRef) and isinstance(bitvec2, z3.BitVecRef):
        if bitvec1.size() < bitvec2.size():
            bitvec1 = P4Cast(bitvec1, bitvec2).eval(p4_vars, expr_chain)
        if bitvec1.size() > bitvec2.size():
            bitvec2 = P4Cast(bitvec2, bitvec1).eval(p4_vars, expr_chain)
    return bitvec1, bitvec2


class P4Z3Class():
    def eval(self, p4_vars, expr_chain):
        raise NotImplementedError("Method eval not implemented!")


class MethodCallExpr(P4Z3Class):

    def __init__(self, expr, *args):
        self.expr = expr
        self.args = args

    def set_args(self, args):
        self.args = args

    def eval(self, p4_vars, expr_chain):
        p4_method = self.expr
        if isinstance(self.expr, str):
            p4_method = p4_vars.resolve_reference(self.expr)
        if callable(p4_method):
            return p4_method(p4_vars, expr_chain, *self.args)
        if isinstance(p4_method, P4Action):
            p4_method.set_param_args(arg_prefix="")
            p4_method.merge_args(p4_vars, expr_chain, self.args)
            return step(p4_vars, [p4_method] + expr_chain)
        raise TypeError(f"Unsupported method type {type(p4_method)}!")


class P4BinaryOp(P4Z3Class):
    def __init__(self, lval, rval, operator):
        self.lval = lval
        self.rval = rval
        self.operator = operator

    def eval(self, p4_vars, expr_chain):
        lval_expr = resolve_expr(p4_vars, expr_chain, self.lval)
        rval_expr = resolve_expr(p4_vars, expr_chain, self.rval)

        # if we have enums, do not use them for operations
        # for some reason, overloading equality does not work here...
        # instead use their current representation...
        lval_expr = check_enum(lval_expr)
        rval_expr = check_enum(rval_expr)
        lval_expr, rval_expr = align_bitvecs(
            lval_expr, rval_expr, p4_vars, expr_chain)
        return self.operator(lval_expr, rval_expr)


class P4UnaryOp(P4Z3Class):
    def __init__(self, val, operator):
        self.val = val
        self.operator = operator

    def eval(self, p4_vars, expr_chain):
        expr = resolve_expr(p4_vars, expr_chain, self.val)
        return self.operator(expr)


class P4not(P4UnaryOp):
    def __init__(self, val):
        operator = z3.Not
        P4UnaryOp.__init__(self, val, operator)


class P4abs(P4UnaryOp):
    def __init__(self, val):
        operator = op.abs
        P4UnaryOp.__init__(self, val, operator)


class P4inv(P4UnaryOp):
    def __init__(self, val):
        operator = op.inv
        P4UnaryOp.__init__(self, val, operator)


class P4neg(P4UnaryOp):
    def __init__(self, val):
        operator = op.neg
        P4UnaryOp.__init__(self, val, operator)


class P4add(P4BinaryOp):
    def __init__(self, lval, rval):
        operator = op.add
        P4BinaryOp.__init__(self, lval, rval, operator)


class P4addsat(P4BinaryOp):
    # TODO: Not sure if this is right, check eventually
    def __init__(self, lval, rval):
        operator = (lambda x, y: z3.BVAddNoOverflow(x, y, False))
        operator = op.add
        P4BinaryOp.__init__(self, lval, rval, operator)


class P4sub(P4BinaryOp):
    def __init__(self, lval, rval):
        operator = op.sub
        P4BinaryOp.__init__(self, lval, rval, operator)


class P4subsat(P4BinaryOp):
    # TODO: Not sure if this is right, check eventually
    def __init__(self, lval, rval):
        operator = (lambda x, y: z3.BVSubNoUnderflow(x, y, False))
        operator = op.sub
        P4BinaryOp.__init__(self, lval, rval, operator)


class P4mul(P4BinaryOp):
    def __init__(self, lval, rval):
        operator = op.mul
        P4BinaryOp.__init__(self, lval, rval, operator)


class P4mod(P4BinaryOp):
    def __init__(self, lval, rval):
        operator = op.mod
        P4BinaryOp.__init__(self, lval, rval, operator)


class P4pow(P4BinaryOp):
    def __init__(self, lval, rval):
        operator = op.pow
        P4BinaryOp.__init__(self, lval, rval, operator)


class P4band(P4BinaryOp):
    def __init__(self, lval, rval):
        operator = op.and_
        P4BinaryOp.__init__(self, lval, rval, operator)


class P4bor(P4BinaryOp):
    def __init__(self, lval, rval):
        operator = op.or_
        P4BinaryOp.__init__(self, lval, rval, operator)


class P4land(P4BinaryOp):
    def __init__(self, lval, rval):
        operator = z3.And
        P4BinaryOp.__init__(self, lval, rval, operator)


class P4lor(P4BinaryOp):
    def __init__(self, lval, rval):
        operator = z3.Or
        P4BinaryOp.__init__(self, lval, rval, operator)


class P4xor(P4BinaryOp):
    def __init__(self, lval, rval):
        operator = op.xor
        P4BinaryOp.__init__(self, lval, rval, operator)


class P4div(P4BinaryOp):
    def __init__(self, lval, rval):
        operator = op.floordiv
        P4BinaryOp.__init__(self, lval, rval, operator)


class P4lshift(P4BinaryOp):
    def __init__(self, lval, rval):
        operator = op.lshift
        P4BinaryOp.__init__(self, lval, rval, operator)


class P4rshift(P4BinaryOp):
    def __init__(self, lval, rval):
        operator = op.rshift
        P4BinaryOp.__init__(self, lval, rval, operator)


class P4lt(P4BinaryOp):
    def __init__(self, lval, rval):
        operator = op.lt
        P4BinaryOp.__init__(self, lval, rval, operator)


class P4le(P4BinaryOp):
    def __init__(self, lval, rval):
        operator = op.le
        P4BinaryOp.__init__(self, lval, rval, operator)


class P4eq(P4BinaryOp):
    def __init__(self, lval, rval):
        operator = op.eq
        P4BinaryOp.__init__(self, lval, rval, operator)


class P4ne(P4BinaryOp):
    def __init__(self, lval, rval):
        operator = op.ne
        P4BinaryOp.__init__(self, lval, rval, operator)


class P4ge(P4BinaryOp):
    def __init__(self, lval, rval):
        operator = op.ge
        P4BinaryOp.__init__(self, lval, rval, operator)


class P4gt(P4BinaryOp):
    def __init__(self, lval, rval):
        operator = op.gt
        P4BinaryOp.__init__(self, lval, rval, operator)


class P4Slice(P4Z3Class):
    def __init__(self, val, slice_l, slice_r):
        self.val = val
        self.slice_l = slice_l
        self.slice_r = slice_r

    def eval(self, p4_vars, expr_chain):
        val_expr = resolve_expr(p4_vars, expr_chain, self.val)
        return z3.Extract(self.slice_l, self.slice_r, val_expr)


class P4Concat(P4Z3Class):
    def __init__(self, lval, rval):
        self.lval = lval
        self.rval = rval

    def eval(self, p4_vars, expr_chain):
        lval_expr = resolve_expr(p4_vars, expr_chain, self.lval)
        rval_expr = resolve_expr(p4_vars, expr_chain, self.rval)
        return z3.Concat(lval_expr, rval_expr)


class P4Cast(P4Z3Class):
    # TODO: need to take a closer look on how to do this correctly...
    # If we cast do we add/remove the least or most significant bits?
    def __init__(self, val, to_size: z3.BitVecSortRef):
        self.val = val
        self.to_size = to_size.size()

    def eval(self, p4_vars, expr_chain):
        expr = resolve_expr(p4_vars, expr_chain, self.val)
        expr = check_bool(expr)

        expr_size = expr.size()
        if expr_size < self.to_size:
            return z3.ZeroExt(self.to_size - expr_size, expr)
        else:
            slice_l = expr_size - 1
            slice_r = expr_size - self.to_size
            return z3.Extract(slice_l, slice_r, expr)


class P4Mux(P4Z3Class):
    def __init__(self, condition, then_val, else_val):
        self.condition = condition
        self.then_val = then_val
        self.else_val = else_val

    def eval(self, p4_vars, expr_chain):
        condition = resolve_expr(p4_vars, expr_chain, self.condition)
        then_val = resolve_expr(p4_vars, expr_chain, self.then_val)
        else_val = resolve_expr(p4_vars, expr_chain, self.else_val)
        return z3.If(condition, then_val, else_val)


class P4Declaration(P4Z3Class):
    # TODO: Add some more declaration checks here.
    # the difference between a P4Declaration and a P4Assignment is that
    # we resolve the variable in the P4Assignment
    # in the declaration we assign variables as is
    # they are resolved at runtime by other classes
    def __init__(self, lval, rval):
        self.lval = lval
        self.rval = rval

    def eval(self, p4_vars, expr_chain):
        p4_vars.set_or_add_var(self.lval, self.rval)
        return step(p4_vars, expr_chain)


class P4StructInitializer(P4Z3Class):
    def __init__(self, z3_reg, name, z3_type, members):
        self.name = name
        self.z3_reg = z3_reg
        self.z3_type = z3_type
        self.members = members

    def eval(self, p4_vars, expr_chain):
        instance = self.z3_reg.instance(self.name, self.z3_type)
        if isinstance(self.members, dict):
            for name, val in self.members.items():
                val_expr = resolve_expr(p4_vars, expr_chain, val)
                instance.set_or_add_var(name, val_expr)
        elif isinstance(self.members, list):
            for index, rval in enumerate(self.members):
                accessor = instance.accessors[index]
                val_expr = resolve_expr(p4_vars, expr_chain, rval)
                instance.set_or_add_var(accessor.name(), val_expr)
        else:
            raise RuntimeError(
                "P4StructInitializer members {members} not supported!")
        return instance


def slice_assign(lval, rval, slice_l, slice_r) -> z3.SortRef:
    lval_max = lval.size() - 1
    if slice_l == lval_max and slice_r == 0:
        return rval
    assemble = []
    if slice_l < lval_max:
        assemble.append(z3.Extract(lval_max, slice_l + 1, lval))
    assemble.append(rval)
    if slice_r > 0:
        assemble.append(z3.Extract(slice_r - 1, 0, lval))
    return z3.Concat(*assemble)


class SliceAssignment(P4Z3Class):
    def __init__(self, lval, rval, slice_l, slice_r):
        self.lval = lval
        self.rval = rval
        self.slice_l = slice_l
        self.slice_r = slice_r

    def eval(self, p4_vars, expr_chain):
        lval_expr = resolve_expr(p4_vars, expr_chain, self.lval)
        rval_expr = resolve_expr(p4_vars, expr_chain, self.rval)
        rval_expr = slice_assign(lval_expr, rval_expr,
                                 self.slice_l, self.slice_r)
        assign = AssignmentStatement(self.lval, rval_expr)
        return step(p4_vars, [assign] + expr_chain)


class AssignmentStatement(P4Z3Class):

    def __init__(self, lval, rval):
        self.lval = lval
        self.rval = rval

    def eval(self, p4_vars, expr_chain):
        log.debug("Assigning %s to %s ", self.rval, self.lval)
        if isinstance(self.rval, list):
            list_expr = []
            for val in self.rval:
                rval_expr = resolve_expr(p4_vars, expr_chain, val)
                # any assignment copies the variable
                # do not pass references
                rval_expr = deepcopy(rval_expr)
                list_expr.append(resolve_expr(p4_vars, expr_chain, val))
            p4_vars.set_list(self.lval, list_expr)
        else:
            rval_expr = resolve_expr(p4_vars, expr_chain, self.rval)
            # any assignment copies the variable
            # do not pass references
            rval_expr = deepcopy(rval_expr)
            if isinstance(rval_expr, int):
                lval = p4_vars.resolve_reference(self.lval)
                rval_expr = z3.BitVecVal(rval_expr, lval.size())
            p4_vars.set_or_add_var(self.lval, rval_expr)
        return step(p4_vars, expr_chain)


class MethodCallStmt(P4Z3Class):

    def __init__(self, method_expr):
        self.method_expr = method_expr

    def eval(self, p4_vars, expr_chain):
        return step(p4_vars, [self.method_expr] + expr_chain)


class BlockStatement(P4Z3Class):

    def __init__(self):
        self.exprs = []

    def add(self, expr):
        self.exprs.append(expr)

    def eval(self, p4_vars, expr_chain):
        return step(p4_vars, self.exprs + expr_chain)


class P4Noop(P4Z3Class):

    def eval(self, p4_vars, expr_chain):
        return step(p4_vars, expr_chain)


class P4Exit(P4Z3Class):

    def eval(self, p4_vars, expr_chain):
        # Exit the chain early
        return step(p4_vars, [])


class P4Action(P4Z3Class):

    def __init__(self):
        self.block = []
        self.params = []
        self.args = []

    def add_parameter(self, is_ref=None, arg_name=None, arg_type=None):
        # TODO: Fix this hack
        if is_ref is None or arg_name is None or arg_type is None:
            return
        self.params.append((is_ref, arg_name, arg_type))

    def add_stmt(self, block):
        if not isinstance(block, BlockStatement):
            raise RuntimeError(f"Expected a block, got {block}!")
        self.block.append(block)

    def get_parameters(self):
        return self.params

    def set_param_args(self, arg_prefix):
        action_args = []
        for param in self.params:
            arg_name = param[1]
            arg_type = param[2]
            if isinstance(arg_type, z3.SortRef):
                action_args.append(
                    z3.Const(f"{arg_prefix}{arg_name}", arg_type))
            else:
                action_args.append(arg_type)
        self.args = action_args

    def merge_args(self, p4_vars, expr_chain, *args):
        if len(*args) > len(self.args):
            raise RuntimeError(
                f"Provided arguments {args} exceeds possible number of parameters.")
        for index, runtime_arg in enumerate(*args):
            self.args[index] = runtime_arg

    def eval(self, p4_vars, expr_chain):
        var_buffer = {}

        # save all the variables that may be overridden
        for param in self.params:
            is_ref = param[0]
            param_name = param[1]
            # previous variables in the environment
            prev_val = p4_vars.get_var(param_name)
            if not is_ref:
                # ignore variables that do not exist
                var_buffer[param_name] = prev_val

        # override the symbolic entries if we have concrete
        # arguments from the table
        for index, arg in enumerate(self.args):
            log.debug("Setting %s as %s ", param_name, arg)
            param_name = self.params[index][1]
            p4_vars.set_or_add_var(param_name, arg)
        # execute the action expression with the new environment
        expr = step(p4_vars, self.block)

        for param in self.params:
            is_ref = param[0]
            param_name = param[1]
            if param_name in var_buffer:
                log.debug("Restoring %s", param_name)
                p4_vars.set_or_add_var(param_name, var_buffer[param_name])
            elif not is_ref:
                log.debug("Deleting %s", param_name)
                p4_vars.del_var(param_name)

        return step(p4_vars, expr_chain, expr)


class P4Extern(P4Action):
    # TODO: This is quite shaky, requires concrete examination
    def __init__(self, name, z3_reg):
        super(P4Extern, self).__init__()
        self.name = name
        self.z3_reg = z3_reg

    def add_method(self, name, method):
        setattr(self, name, method)

    def eval(self, p4_vars, expr_chain):

        for index, arg in enumerate(self.args):
            is_ref = self.params[index][0]
            param_name = self.params[index][1]

            log.debug("Setting %s as %s ", param_name, arg)
            # Because we do not know what the extern is doing
            # we initiate a new z3 const and just overwrite all reference types
            if is_ref:
                # Externs often have generic types until they are called
                # This call resolves the argument and gets its z3 type
                arg_type = get_type(p4_vars, expr_chain, arg)
                extern_mod = z3.Const(f"{self.name}_{param_name}", arg_type)
                instance = self.z3_reg.instance(
                    f"{self.name}_{param_name}", arg_type)
                # In the case that the instance is a complex type make sure
                # to propagate the variable through all its members
                if isinstance(instance, P4ComplexType):
                    instance.propagate_type(extern_mod)
                # Finally, assign a new value to the pass-by-reference argument
                p4_vars.set_or_add_var(arg, instance)

        return step(p4_vars, expr_chain)


class P4Control(P4Action):

    def __init__(self):
        super(P4Control, self).__init__()
        self.locals = []
        self.p4_vars = None

    def declare_local(self, local_name, local):
        self.locals.append((local_name, local))

    def add_args(self, params):
        self.params = params

    def add_instance(self, z3_reg, name, params):
        self.params = params
        self.p4_vars = z3_reg.init_p4_state(name, params)

    def add_apply_stmt(self, stmt):
        self.block.append(stmt)

    def apply(self, p4_vars, expr_chain, *p4_args):
        self.args = p4_args
        return self.eval(p4_vars, expr_chain)

    def eval(self, p4_vars=None, expr_chain=[]):
        if not p4_vars:
            # There is no state yet, so use the state of the function
            p4_vars = self.p4_vars
        p4_vars_tmp = self.p4_vars

        local_decls = []
        for local in self.locals:
            decl = P4Declaration(local[0], local[1])
            local_decls.append(decl)
        self.block = local_decls + self.block

        var_buffer = {}

        # save all the variables that may be overridden
        for param in self.params:
            is_ref = param[0]
            param_name = param[1]
            # previous variables in the environment
            prev_val = p4_vars.get_var(param_name)
            var_buffer[param_name] = prev_val

        # override the symbolic entries if we have concrete
        # arguments from the table
        for index, arg in enumerate(self.args):
            var = p4_vars.get_var(arg)
            log.debug("Setting %s as %s ", param_name, arg)
            param_name = self.params[index][1]
            p4_vars_tmp.set_or_add_var(param_name, var)
        # p4_vars_tmp.propagate_type(p4_vars.const)
        # execute the action expression with the new environment
        expr = step(p4_vars_tmp, self.block)
        for param in self.params:
            is_ref = param[0]
            param_name = param[1]
            if var_buffer[param_name] is not None:
                log.debug("Restoring %s", param_name)
                p4_vars.set_or_add_var(param_name, var_buffer[param_name])
            else:
                log.debug("Deleting %s", param_name)
                p4_vars.del_var(param_name)
        return step(p4_vars, expr_chain, expr)


class P4Parser(P4Control):

    def __init__(self):
        super(P4Parser, self).__init__()


class IfStatement(P4Z3Class):

    def __init__(self):
        self.cond = None
        self.then_block = None
        self.else_block = None

    def add_condition(self, cond):
        self.cond = cond

    def add_then_stmt(self, stmt):
        self.then_block = stmt

    def add_else_stmt(self, stmt):
        self.else_block = stmt

    def eval(self, p4_vars, expr_chain):
        if self.cond is None:
            raise RuntimeError("Missing condition!")
        cond = resolve_expr(p4_vars, expr_chain, self.cond)
        then_p4_vars = deepcopy(p4_vars)
        then_expr = step(then_p4_vars, [self.then_block] + expr_chain)
        if self.else_block:
            else_p4_vars = deepcopy(p4_vars)
            else_expr = step(else_p4_vars, [self.else_block] + expr_chain)
            return z3.If(cond, then_expr, else_expr)
        else:
            return z3_implies(p4_vars, expr_chain, cond, then_expr)


class SwitchHit(P4Z3Class):
    def __init__(self, table, cases, default_case):
        self.table = table
        self.default_case = default_case
        self.cases = cases

    def eval_loop(self, p4_vars, expr_chain, cases):
        p4_vars_copy = deepcopy(p4_vars)
        if cases:
            _, case = cases.popitem(last=False)
            case_expr = step(
                p4_vars_copy, [case["case_block"]] + expr_chain)
            then_expr = self.eval_loop(p4_vars, expr_chain, cases)
            return z3.If(case["match"], case_expr, then_expr)
        else:
            return step(p4_vars_copy, [self.default_case] + expr_chain)

    def eval_switch_matches(self, table):
        for case_name, case in self.cases.items():
            match_var = case["match_var"]
            action = table.actions[case_name][0]
            self.cases[case_name]["match"] = (match_var == action)

    def eval(self, p4_vars, expr_chain):
        self.eval_switch_matches(self.table)
        switch_hit = self.eval_loop(p4_vars, expr_chain, self.cases.copy())
        return switch_hit


class SwitchStatement(P4Z3Class):
    # TODO: Fix fall through for switch statement, purge this terrible code
    def __init__(self, table_str):
        self.table_str = table_str
        self.default_case = BlockStatement()
        self.cases = OrderedDict()

    def add_case(self, action_str):
        # skip default statements, they are handled separately
        if action_str == "default":
            return
        case = {}
        case["match_var"] = z3.Int(f"{self.table_str}_action")
        case["case_block"] = BlockStatement()
        self.cases[action_str] = case

    def add_stmt_to_case(self, action_str, case_stmt):
        if action_str == "default":
            self.default_case.add(case_stmt)
        else:
            case_block = self.cases[action_str]["case_block"]
            case_block.add(case_stmt)

    def eval_loop(self, p4_vars, expr_chain, cases):
        p4_vars_copy = deepcopy(p4_vars)
        if cases:
            _, case = cases.popitem(last=False)
            case_expr = step(p4_vars_copy, [case["case_block"]] + expr_chain)
            then_expr = self.eval_loop(p4_vars, expr_chain, cases)
            return z3.If(case["match"], case_expr, then_expr)
        else:
            return step(p4_vars_copy, [self.default_case] + expr_chain)

    def eval_switch_matches(self, table):
        for case_name, case in self.cases.items():
            match_var = case["match_var"]
            action = table.actions[case_name][0]
            self.cases[case_name]["match"] = (match_var == action)

    def eval(self, p4_vars, expr_chain):
        table = p4_vars.get_var(self.table_str)
        switch_hit = SwitchHit(table, self.cases.copy(), self.default_case)
        return step(p4_vars, [table, switch_hit] + expr_chain)


class P4Table(P4Z3Class):

    def __init__(self, name):
        self.name = name
        self.keys = []
        self.const_entries = []
        self.actions = OrderedDict()
        self.default_action = None

    def add_action(self, action_expr):
        action_name, action_args = resolve_action(action_expr)
        index = len(self.actions) + 1
        self.actions[action_name] = (index, action_name, action_args)

    def add_default(self, action_expr):
        action_name, action_args = resolve_action(action_expr)
        self.default_action = (0, action_name, action_args)

    def add_match(self, table_key):
        self.keys.append(table_key)

    def add_const_entry(self, const_keys, action_expr):

        if len(self.keys) != len(const_keys):
            raise RuntimeError("Constant keys must match table keys!")
        action_name, action_args = resolve_action(action_expr)
        self.const_entries.append((const_keys, (action_name, action_args)))

    def apply(self, p4_vars, expr_chain):
        return step(p4_vars, [self] + expr_chain)

    def eval_keys(self, p4_vars, expr_chain):
        key_pairs = []
        if not self.keys:
            # there is nothing to match with...
            return z3.BoolVal(False)
        for index, key in enumerate(self.keys):
            key_eval = resolve_expr(p4_vars, expr_chain, key)
            key_match = z3.Const(f"{self.name}_key_{index}", key_eval.sort())
            key_pairs.append(key_eval == key_match)
        return z3.And(key_pairs)

    def eval_action(self, p4_vars, expr_chain, action_tuple):
        p4_action = action_tuple[0]
        p4_action_args = action_tuple[1]
        p4_action = p4_vars.get_var(p4_action)
        if not isinstance(p4_action, P4Action):
            raise TypeError(f"Expected a P4Action got {type(p4_action)}!")
        p4_vars = deepcopy(p4_vars)
        p4_action = deepcopy(p4_action)
        p4_action.set_param_args(arg_prefix=self.name)
        p4_action.merge_args(p4_vars, expr_chain, p4_action_args)
        return step(p4_vars, [p4_action] + expr_chain)

    def eval_default(self, p4_vars, expr_chain):
        if self.default_action is None:
            # In case there is no default action, the first action is default
            self.default_action = (0, "NoAction", [])
        _, action_name, p4_action_args = self.default_action
        return self.eval_action(p4_vars, expr_chain,
                                (action_name, p4_action_args))

    def eval_const_loop(self, p4_vars, expr_chain, const_entries):
        if not const_entries:
            return self.eval_default(p4_vars, expr_chain)

        const_keys, action = const_entries.pop(0)
        p4_action = action[0]
        p4_action_args = action[1]
        matches = []
        for index, key in enumerate(self.keys):
            key_eval = resolve_expr(p4_vars, expr_chain, key)
            matches.append(key_eval == const_keys[index])
        action_match = z3.And(*matches)
        action_expr = self.eval_action(p4_vars, expr_chain,
                                       (p4_action, p4_action_args))
        then_expr = self.eval_const_loop(
            p4_vars, expr_chain, const_entries)
        return z3.If(action_match, action_expr, then_expr)

    def eval_table_loop(self, p4_vars, expr_chain, actions):
        if not actions:
            const_entries = self.const_entries.copy()
            return self.eval_const_loop(p4_vars, expr_chain, const_entries)
        action = z3.Int(f"{self.name}_action")
        _, f_tuple = actions.popitem(last=False)
        p4_action_id = f_tuple[0]
        action_name = f_tuple[1]
        p4_action_args = f_tuple[2]
        action_expr = self.eval_action(p4_vars, expr_chain,
                                       (action_name, p4_action_args))
        action_match = (action == z3.IntVal(p4_action_id))
        then_expr = self.eval_table_loop(p4_vars, expr_chain, actions)
        return z3.If(action_match, action_expr, then_expr)

    def eval(self, p4_vars, expr_chain):
        # This is a table match where we look up the provided key
        # If we match select the associated action,
        # else use the default action
        tbl_match = self.eval_keys(p4_vars, expr_chain)
        actions = self.actions.copy()
        table_expr = self.eval_table_loop(p4_vars, expr_chain, actions)
        def_expr = self.eval_default(p4_vars, expr_chain)
        return z3.If(tbl_match, table_expr, def_expr)
