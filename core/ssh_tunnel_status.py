def tunnel_endpoint(spec) -> str:
    return f"{spec.bind_host}:{spec.bind_port}"


def tunnel_target(spec) -> str:
    if spec.kind == "D":
        return "SOCKS proxy"
    return f"{spec.target_host}:{spec.target_port}"


def forwarder_status(index: int, forwarder) -> dict:
    spec = forwarder.spec
    return {
        "index": index,
        "label": spec.label,
        "kind": spec.kind,
        "endpoint": tunnel_endpoint(spec),
        "target": tunnel_target(spec),
        "active": forwarder.active,
    }
