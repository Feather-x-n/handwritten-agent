import inspect
class SecurityError(Exception):
    """工具拒绝执行危险操作时抛出，由 runtime 记 trace 并返回给模型。"""
TOOL_REGISTRY = {}
 
_TYPE_MAP = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
}
 
 
def tool(func=None, *, confirm=False):
    def register(f):
        sig = inspect.signature(f)
  
        properties = {}
        required = []
  
        for name, param in sig.parameters.items():
            py_type = param.annotation
            json_type = _TYPE_MAP.get(py_type, "string")
  
            properties[name] = {"type": json_type, "description": ""}
  
            if param.default is inspect.Parameter.empty:
                required.append(name)
  
        schema = {
            "type": "function",
            "function": {
                "name": f.__name__,
                "description": (f.__doc__ or "").strip(),
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        }
  
        f.requires_confirm = confirm
        TOOL_REGISTRY[f.__name__] = (f, schema)
        return f

    if func is None:
        return register
    return register(func)
 
 
def get_schemas():
    return [schema for _, schema in TOOL_REGISTRY.values()]
 
 
def get_impls():
    return {name: func for name, (func, _) in TOOL_REGISTRY.items()}