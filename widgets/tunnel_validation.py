from core.ssh_tunnels import parse_tunnel_spec


def validate_tunnel_lines(text: str) -> tuple[list[str], str]:
    tunnels: list[str] = []
    previews: list[str] = []
    for line_no, raw in enumerate((text or "").splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        try:
            spec = parse_tunnel_spec(line)
        except ValueError as e:
            return [], f"Line {line_no}: {e}"
        tunnels.append(line)
        target = "SOCKS proxy" if spec.kind == "D" else f"{spec.target_host}:{spec.target_port}"
        previews.append(f"{spec.kind} {spec.bind_host}:{spec.bind_port} -> {target}")
    if not tunnels:
        return [], "No tunnels configured"
    return tunnels, "; ".join(previews)
