"""Output paths under one root (T7).

Usage:
    from src.paths import apply_output_root
    config = apply_output_root(config)

A config may set analysis.output_root (optional, default
"outputs"). Every output path the config lists — the load
outputs in input.files, the stage outputs in
analysis.outputs, and the conversion outputs in
conversion_breakdown.outputs — is rewritten under that root
by replacing its leading "outputs/" part. A config without
output_root, or with output_root "outputs", is unchanged, so
the restaurant paths stay exactly as they are.

Input paths (input.files day/month path, and the conversion
export path) are NOT rewritten: they point at the files that
were exported or generated, wherever they are.
"""

DEFAULT_ROOT = "outputs"


def apply_output_root(config):
    """Rewrite the config's output paths under output_root.

    Returns the same dict, with paths changed in place. Only
    paths starting with "outputs/" are rewritten.
    """
    analysis = config.get("analysis") or {}
    root = analysis.get("output_root") or DEFAULT_ROOT
    if root == DEFAULT_ROOT:
        return config

    def rewrite(path):
        if isinstance(path, str) and path.startswith(DEFAULT_ROOT + "/"):
            return root + path[len(DEFAULT_ROOT):]
        return path

    for entry in (config.get("input") or {}).get("files", {}).values():
        if isinstance(entry, dict) and "output" in entry:
            entry["output"] = rewrite(entry["output"])
    for key in (analysis.get("outputs") or {}):
        analysis["outputs"][key] = rewrite(analysis["outputs"][key])
    breakdown = config.get("conversion_breakdown") or {}
    for key in (breakdown.get("outputs") or {}):
        breakdown["outputs"][key] = rewrite(
            breakdown["outputs"][key])
    return config
