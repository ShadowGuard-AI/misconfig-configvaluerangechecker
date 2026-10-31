![Banner](banner.png)

# misconfig-ConfigValueRangeChecker
Enforces value ranges and types for configuration parameters based on a simple rule set. Prevents misconfigurations caused by out-of-range values or incorrect data types. - Focused on Check for misconfigurations in configuration files or infrastructure definitions

A parameter name may be a dotted path such as `database.port`, which is resolved through nested mappings. A ruled parameter that is absent from the configuration is invalid and fails the run. A boolean never passes an integer or float rule. For a string rule, `min` and `max` are length bounds. A rule whose type is not one of integer, float, string, boolean, or list is a rules error and fails the run. The rules file must contain a JSON list of rule objects; any other top level shape is reported as a rules error, not a traceback.

## Install
`git clone https://github.com/ShadowStrikeHQ/misconfig-configvaluerangechecker`
`pip install -r requirements.txt`

## Usage
`python3 main.py -c <config_file> -r <rules_file>`

## Parameters
- `-h`: Show help message and exit
- `-c`, `--config`: Path to the configuration file (JSON or YAML).
- `-r`, `--rules`: Path to the rules file (JSON, a list of rule objects).

## License
Copyright (c) ShadowStrikeHQ
