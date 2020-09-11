import argparse
from pathlib import Path
import os
import sys
import logging
import z3
from get_semantics import get_z3_formulization
import p4z3.util as util
sys.setrecursionlimit(15000)


FILE_DIR = os.path.dirname(os.path.abspath(__file__))
log = logging.getLogger(__name__)

# We maintain a list of passes to skip for convenience
# This reduces the amount of noise when generating random programs
SKIPPED_PASSES = []


def needs_skipping(post):
    for skip_pass in SKIPPED_PASSES:
        if skip_pass in post:
            log.warning("Skipping \"%s\" pass...", skip_pass)
            return True
    return False


def debug_msg(p4_files):
    debug_string = "You can debug this failure by running:\n"
    debug_string += f"python3 {FILE_DIR}/{Path(__file__).stem}.py --progs "
    for p4_file in p4_files:
        p4_file_name = p4_file.stem
        p4_file_dir = p4_file.parent
        debug_string += f" {p4_file_dir}/failed/{p4_file_name} "
    log.error(debug_string)


def handle_pyz3_error(fail_dir, p4_file):
    util.check_dir(fail_dir)
    failed = [p4_file.with_suffix(".py"), p4_file.with_suffix(".p4")]
    util.copy_file(failed, fail_dir)


def has_undefined_behavior(z3_formula):

    if z3.is_const(z3_formula):
        if z3.z3util.is_expr_val(z3_formula):
            return False
        else:  # variable
            return str(z3_formula) == "undefined"

    else:
        for child in z3_formula.children():
            result = has_undefined_behavior(child)
            if result:
                return result

        return False


nondets = []


def substitute_undefined(z3_formula):
    if z3_formula.decl().kind() == z3.Z3_OP_ITE:
        cond_expr = z3_formula.children()[0]
        then_expr = z3_formula.children()[1]
        else_expr = z3_formula.children()[2]
        cond_expr, cond_has_undefined = substitute_undefined(cond_expr)
        then_expr, then_has_undefined = substitute_undefined(then_expr)
        else_expr, else_has_undefined = substitute_undefined(else_expr)
        if then_has_undefined and else_has_undefined:
            nondet = z3.FreshConst(then_expr.sort(), "nondet")
            nondets.append(nondet)
            return nondet, True
        return z3.If(cond_expr, then_expr, else_expr), False

    if isinstance(z3_formula, z3.DatatypeRef):
        decl = z3_formula.decl()
        child_list = z3_formula.children()
        for idx, child in enumerate(child_list):
            child, has_undefined = substitute_undefined(child)
            if has_undefined:
                child = z3.FreshConst(child.sort(), "nondet")
                nondets.append(child)
            child_list[idx] = child
        return decl(*child_list), False

    if z3.is_const(z3_formula):
        # variable
        if not z3.z3util.is_expr_val(z3_formula):
            if str(z3_formula) == "undefined":
                nondet = z3.FreshConst(z3_formula.sort(), "nondet")
                nondets.append(nondet)
                return nondet, True

    decl = z3_formula.decl()
    child_list = z3_formula.children()
    for idx, child in enumerate(child_list):
        child, has_undefined = substitute_undefined(child)
        if has_undefined:
            nondet = z3.FreshConst(z3_formula.sort(), "nondet")
            nondets.append(nondet)
            return nondet, has_undefined
        child_list[idx] = child
    if child_list:
        if decl.kind() == z3.Z3_OP_AND:
            return z3.And(*child_list), False
        if decl.kind() == z3.Z3_OP_OR:
            return z3.Or(*child_list), False
        return decl(*child_list), False
    return z3_formula, False


def check_equivalence(prog_before, prog_after, allow_undef):
    # The equivalence check of the solver
    # For all input packets and possible table matches the programs should
    # be the same
    try:
        # the equivalence equation
        log.debug("Simplifying equation...")
        tv_equiv = z3.simplify(prog_before != prog_after)
    except z3.Z3Exception as e:
        prog_before_simpl = z3.simplify(prog_before)
        prog_after_simpl = z3.simplify(prog_after)
        log.error("Failed to compare z3 formulas!\nReason: %s", e)
        log.error("PROGRAM BEFORE\n%s", prog_before_simpl)
        log.error("PROGRAM AFTER\n%s", prog_after_simpl)
        return util.EXIT_VIOLATION
    log.debug("Checking...")
    log.debug(z3.tactics())
    t = z3.Then(
        z3.Tactic("simplify"),
        # z3.Tactic("distribute-forall"),
        # z3.Tactic("ackermannize_bv"),
        # z3.Tactic("bvarray2uf"),
        # z3.Tactic("card2bv"),
        # z3.Tactic("propagate-bv-bounds-new"),
        # z3.Tactic("reduce-bv-size"),
        # z3.Tactic("qe_rec"),
        z3.Tactic("smt"),
    )

    s = t.solver()
    log.debug(s.sexpr())
    ret = s.check(tv_equiv)
    log.debug(tv_equiv)
    log.debug(ret)
    if allow_undef and ret == z3.sat:
        log.info("Detected difference in undefined behavior. "
                 "Rechecking with undefined variables ignored.")
        prog_before = z3.simplify(prog_before)
        prog_after = z3.simplify(prog_after)
        prog_before, _ = substitute_undefined(prog_before)
        if not nondets:
            tv_equiv = prog_before != prog_after
        else:
            tv_equiv = z3.ForAll(nondets, prog_before != prog_after)
        # check equivalence of the sub clause
        ret = s.check(tv_equiv)

    if ret == z3.sat:
        prog_before_simpl = z3.simplify(prog_before)
        prog_after_simpl = z3.simplify(prog_after)
        log.error("Detected an equivalence violation!")
        log.error("PROGRAM BEFORE\n%s", prog_before_simpl)
        log.error("PROGRAM AFTER\n%s", prog_after_simpl)
        log.error("Proposed solution:")
        log.error(s.model())
        return util.EXIT_VIOLATION
    else:
        return util.EXIT_SUCCESS


def z3_check(prog_paths, fail_dir=None, allow_undef=False):
    if len(prog_paths) < 2:
        log.error("Equivalence checks require at least two input programs!")
        return util.EXIT_FAILURE
    z3_progs = []
    for p4_prog in prog_paths:
        p4_path = Path(p4_prog)
        package, result = get_z3_formulization(p4_path)
        if result != util.EXIT_SUCCESS:
            if fail_dir and result != util.EXIT_SKIPPED:
                handle_pyz3_error(fail_dir, p4_path)
                debug_msg([p4_path, p4_path])
            return result
        pipes = package.get_pipes()
        z3_progs.append((p4_path, pipes))
    for idx in range(1, len(z3_progs)):
        p4_pre_path, pipes_pre = z3_progs[idx - 1]
        p4_post_path, pipes_post = z3_progs[idx]
        log.info("\nComparing programs\n%s\n%s\n########",
                 p4_pre_path.stem, p4_post_path.stem)
        # sometimes we want to skip a specific pass
        if needs_skipping(str(p4_post_path)):
            continue
        if len(pipes_pre) != len(pipes_post):
            log.warning("Pre and post model differ in size!")
            return util.EXIT_SKIPPED
        for pipe_name in pipes_pre:
            pipe_pre = pipes_pre[pipe_name][0]
            pipe_post = pipes_post[pipe_name][0]
            log.info("Checking z3 equivalence for pipe %s...", pipe_name)
            ret = check_equivalence(pipe_pre, pipe_post, allow_undef)
            if ret != util.EXIT_SUCCESS:
                if fail_dir:
                    handle_pyz3_error(fail_dir, p4_pre_path)
                    handle_pyz3_error(fail_dir, p4_post_path)
                    debug_msg([p4_pre_path, p4_post_path])
                return ret
    log.info("Passed all checks!")
    return util.EXIT_SUCCESS


def main(args=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--progs", "-p", dest="progs",
                        type=str, nargs='+', required=True,
                        help="The ordered list of programs to compare.")
    parser.add_argument("-u", "--allow_undefined", dest="allow_undef",
                        action="store_true",
                        help="Ignore changes in undefined behavior.")
    args = parser.parse_args(args)
    return z3_check(args.progs, None, args.allow_undef)


if __name__ == '__main__':
    # configure logging
    logging.basicConfig(filename="analysis.log",
                        format="%(levelname)s:%(message)s",
                        level=logging.INFO,
                        filemode='w')
    stderr_log = logging.StreamHandler()
    stderr_log.setFormatter(logging.Formatter("%(levelname)s:%(message)s"))
    logging.getLogger().addHandler(stderr_log)
    main()
