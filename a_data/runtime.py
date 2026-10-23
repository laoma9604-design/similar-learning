"""Portable closed-form object evaluation. No eval(), network, or reference labels.

Object format follows case-fixtures.json: ``function`` is a single string written with
node IDs, ``baseline`` / ``input_scales`` are lists aligned to ``controllable_inputs``,
``baseline_output`` / ``output_scale`` are scalars (single output).

This evaluator helps C integrate data; it is not TopoAdv or an audit/search engine.
"""
import ast
import math
from functools import lru_cache


@lru_cache(maxsize=256)
def parse(expression):
    return ast.parse(expression, mode="eval").body


def expression_value(expression, values):
    def visit(node):
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            return float(node.value)
        if isinstance(node, ast.Name):
            return values[node.id]
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
            value = visit(node.operand)
            return -value if isinstance(node.op, ast.USub) else value
        if isinstance(node, ast.BinOp):
            left, right = visit(node.left), visit(node.right)
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            if isinstance(node.op, ast.Div):
                return left / right
            if isinstance(node.op, ast.Pow):
                return left ** right
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "exp" and len(node.args) == 1 and not node.keywords):
            return math.exp(visit(node.args[0]))
        raise ValueError("Unsupported expression syntax: " + ast.dump(node))

    result = visit(parse(expression))
    if not math.isfinite(result):
        raise ValueError("Non-finite function output")
    return result


def evaluate_object(obj, inputs):
    if set(inputs) != set(obj["controllable_inputs"]):
        raise ValueError("Input IDs must exactly match controllable_inputs")
    values = dict(inputs)
    for node_id, value in inputs.items():
        lo, hi = obj["legal_domain"][node_id]
        lo = -math.inf if lo is None else lo
        hi = math.inf if hi is None else hi
        if not math.isfinite(value) or not lo - 1e-12 <= value <= hi + 1e-12:
            raise ValueError("Input outside legal domain: " + node_id)
    output_id = obj["designated_outputs"][0]
    values[output_id] = expression_value(obj["function"], values)
    return {output_id: values[output_id]}


def intervene(obj, u_by_node):
    if set(u_by_node) != set(obj["controllable_inputs"]):
        raise ValueError("Dimensionless intervention must specify every input ID")
    inputs = {}
    for i, node_id in enumerate(obj["controllable_inputs"]):
        u = u_by_node[node_id]
        lo, hi = obj["intervention_bounds"][node_id]
        if not math.isfinite(u) or not lo - 1e-12 <= u <= hi + 1e-12:
            raise ValueError("Intervention outside bounds: " + node_id)
        inputs[node_id] = obj["baseline"][i] + obj["input_scales"][i] * u
    return inputs


def normalized_response(obj, u_by_node):
    output_id = obj["designated_outputs"][0]
    outputs = evaluate_object(obj, intervene(obj, u_by_node))
    return {output_id: (outputs[output_id] - obj["baseline_output"]) / obj["output_scale"]}
