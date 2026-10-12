"""Files G1 installs into the host's configuration root (design 9.1): always-on rules, situational rules and the
g1 skill. FILES lists them relative to this package; the same relative paths are used under the host's configuration
root. Their text is read through pkgutil (only at install and self-heal), so it loads from the source tree and from
the zipapp alike. FILES is a constant so that the per-call hooks never import pkgutil."""

FILES = (
    "rules/g1.md",
    "rules/g1-instinct.md",
    "rules/g1-work.md",
    "rules/g1-writing.md",
    "rules/g1-korean.md",
    "skills/g1/SKILL.md",
)
