REMOTE_MONITOR_COMMAND = r"""
host=$(hostname -s 2>/dev/null || hostname 2>/dev/null || printf unknown)
printf 'host=%s\n' "$host"
awk '/MemTotal/{t=$2}/MemAvailable/{a=$2}END{if(t>0)printf "mem=%.2f/%.2f GB\n",(t-a)/1048576,t/1048576}' /proc/meminfo 2>/dev/null
if command -v vmstat >/dev/null 2>&1; then
  vmstat 1 2 | awk 'END{if($15!="")printf "cpu=%d%%\n",100-$15}'
else
  awk '{printf "cpu=load %s\n",$1}' /proc/loadavg 2>/dev/null
fi
uptime -p 2>/dev/null | sed 's/^/uptime=/'
df -P / /tmp /boot/efi 2>/dev/null | awk 'NR>1{printf "disk=%s:%s\n",$6,$5}'
awk -F'[: ]+' '$2!="lo"{rx+=$3; tx+=$11}END{printf "net=%s %s\n",rx+0,tx+0}' /proc/net/dev 2>/dev/null
"""


def parse_remote_monitor_output(output: str) -> dict:
    metrics: dict[str, object] = {"disk": []}
    for line in output.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if key == "disk":
            metrics.setdefault("disk", [])
            metrics["disk"].append(value)
        elif key == "net":
            parts = value.split()
            if len(parts) >= 2:
                try:
                    metrics["net"] = (int(parts[0]), int(parts[1]))
                except ValueError:
                    pass
        else:
            metrics[key] = value
    return metrics


def format_rate(bytes_per_second: float) -> str:
    units = ("B/s", "KB/s", "MB/s", "GB/s")
    value = float(bytes_per_second)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            if unit == "B/s":
                return f"{value:.0f} {unit}"
            return f"{value:.2f} {unit}"
        value /= 1024
    return f"{value:.2f} GB/s"


def format_bytes(byte_count: int | float) -> str:
    units = ("B", "KB", "MB", "GB", "TB")
    value = float(byte_count)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{value:.0f} {unit}"
            return f"{value:.2f} {unit}"
        value /= 1024
    return f"{value:.2f} TB"


def format_remote_monitor_details(
    metrics: dict | None,
    *,
    down_rate: float | None = None,
    up_rate: float | None = None,
    status: str | None = None,
) -> str:
    if status:
        return f"Remote monitor\nStatus: {status}"
    if not metrics:
        return "Remote monitor\nStatus: idle"
    if metrics.get("error"):
        return f"Remote monitor\nStatus: error\nDetails: {metrics.get('error')}"

    lines = ["Remote monitor"]
    lines.append(f"Host: {metrics.get('host') or 'Remote'}")
    lines.append(f"CPU: {metrics.get('cpu') or '--'}")
    lines.append(f"Memory: {metrics.get('mem') or '--'}")
    if down_rate is not None or up_rate is not None:
        lines.append(f"Network down: {format_rate(down_rate or 0)}")
        lines.append(f"Network up: {format_rate(up_rate or 0)}")
    uptime = str(metrics.get("uptime") or "--").replace("up ", "")
    lines.append(f"Uptime: {uptime}")

    disks = metrics.get("disk") or []
    if disks:
        lines.append("Disks:")
        lines.extend(f"  {disk}" for disk in disks)
    else:
        lines.append("Disks: --")
    return "\n".join(lines)
