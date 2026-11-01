import argparse
import json
import logging
import os
import sys
import yaml

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class ConfigValueRangeChecker:
    """
    Enforces value ranges and types for configuration parameters based on a rule set.
    Prevents misconfigurations caused by out-of-range values or incorrect data types.
    """

    def __init__(self, config_file, rules_file):
        """
        Initializes the ConfigValueRangeChecker with configuration and rules files.

        Args:
            config_file (str): Path to the configuration file (JSON or YAML).
            rules_file (str): Path to the rules file (JSON).
        """
        self.config_file = config_file
        self.rules_file = rules_file
        self.config_data = None
        self.rules_data = None

    def load_config(self):
        """
        Loads the configuration data from the specified file.
        Supports JSON and YAML formats.

        Returns:
            bool: True if the configuration was loaded successfully, False otherwise.
        """
        try:
            with open(self.config_file, 'r') as f:
                file_extension = os.path.splitext(self.config_file)[1].lower()
                if file_extension == '.json':
                    self.config_data = json.load(f)
                elif file_extension == '.yaml' or file_extension == '.yml':
                    self.config_data = yaml.safe_load(f)  # Use safe_load for security
                else:
                    logging.error(f"Unsupported configuration file format: {file_extension}")
                    return False
            logging.info(f"Configuration loaded from {self.config_file}")
            return True
        except FileNotFoundError:
            logging.error(f"Configuration file not found: {self.config_file}")
            return False
        except json.JSONDecodeError as e:
            logging.error(f"Error decoding JSON in configuration file: {e}")
            return False
        except yaml.YAMLError as e:
            logging.error(f"Error decoding YAML in configuration file: {e}")
            return False
        except Exception as e:
            logging.error(f"Error loading configuration file: {e}")
            return False


    def load_rules(self):
        """
        Loads the rules data from the specified JSON file.

        Returns:
            bool: True if the rules were loaded successfully, False otherwise.
        """
        try:
            with open(self.rules_file, 'r') as f:
                self.rules_data = json.load(f)
            logging.info(f"Rules loaded from {self.rules_file}")
            return True
        except FileNotFoundError:
            logging.error(f"Rules file not found: {self.rules_file}")
            return False
        except json.JSONDecodeError as e:
            logging.error(f"Error decoding JSON in rules file: {e}")
            return False
        except Exception as e:
            logging.error(f"Error loading rules file: {e}")
            return False

    def _resolve_parameter(self, parameter):
        """
        Resolves a parameter name against the configuration data,
        walking nested mappings for a dotted name such as
        database.port.

        Returns:
            tuple: (True, value) when the parameter is present,
            (False, None) when any step of the path is absent.
        """
        if not isinstance(parameter, str) or not parameter:
            return False, None
        current = self.config_data
        for part in parameter.split('.'):
            if not isinstance(current, dict) or part not in current:
                return False, None
            # Each part must be a mapping key exactly as written. A key
            # that itself contains a dot cannot be named by a rule, and a
            # list index cannot be a step, so parameters inside lists are
            # outside what a rule can reach.
            current = current[part]
        return True, current

    def validate_config(self):
        """
        Validates the configuration data against the loaded rules.

        Returns:
            bool: True if the configuration is valid, False otherwise.
        """
        # This tests the loaded value, not whether loading happened,
        # so a config that loaded as an empty mapping and a rules file
        # that loaded as an empty list both report themselves as not
        # loaded. An empty rules list therefore fails the run rather
        # than meaning no rules, and the message points at the wrong
        # cause.
        if not self.config_data:
            logging.error("Configuration data is not loaded.")
            return False
        if not self.rules_data:
            logging.error("Rules data is not loaded.")
            return False

        # The rules file must hold a list of rule objects. Any other
        # shape is a rules error with a plain statement, not a traceback.
        if not isinstance(self.rules_data, list) or not all(
            isinstance(rule, dict) for rule in self.rules_data
        ):
            logging.error("Rules file must contain a JSON list of rule objects, each with parameter, type, and optional min and max fields.")
            return False

        is_valid = True
        for rule in self.rules_data:
            parameter = rule.get('parameter')
            data_type = rule.get('type')
            min_value = rule.get('min')
            max_value = rule.get('max')

            known_types = ('integer', 'float', 'string', 'boolean', 'list')
            if data_type not in known_types:
                logging.error(f"Rule for parameter '{parameter}' has unknown type '{data_type}'. Known types are: {', '.join(known_types)}.")
                is_valid = False
                continue

            try:
                # Resolve the parameter, walking nested mappings for a
                # dotted name such as database.port. A ruled parameter
                # that is absent from the configuration is invalid.
                found, value = self._resolve_parameter(parameter)

                if not found:
                    logging.error(f"Parameter '{parameter}' not found in configuration. A ruled parameter that is absent is invalid.")
                    is_valid = False
                    continue

                # Type validation. bool is a subclass of int in Python,
                # so booleans are rejected explicitly for numeric rules:
                # true must not pass an integer rule as the value 1.
                if data_type == 'integer':
                    # A parameter present with a null value reaches these tests
                    # and fails whichever type the rule names, so it is reported
                    # as the wrong type rather than as a parameter holding
                    # nothing. The distinction matters when an author left a
                    # placeholder null on purpose to be filled in later.
                    if isinstance(value, bool) or not isinstance(value, int):
                        logging.error(f"Parameter '{parameter}' has incorrect type. Expected integer, got {type(value).__name__}.")
                        is_valid = False
                        continue
                elif data_type == 'float':
                    if isinstance(value, bool) or not isinstance(value, (int, float)):  # Allow int to be converted to float
                        logging.error(f"Parameter '{parameter}' has incorrect type. Expected float, got {type(value).__name__}.")
                        is_valid = False
                        continue
                elif data_type == 'string':
                    if not isinstance(value, str):
                        logging.error(f"Parameter '{parameter}' has incorrect type. Expected string, got {type(value).__name__}.")
                        is_valid = False
                        continue
                elif data_type == 'boolean':
                    if not isinstance(value, bool):
                        logging.error(f"Parameter '{parameter}' has incorrect type. Expected boolean, got {type(value).__name__}.")
                        is_valid = False
                        continue
                elif data_type == 'list':
                    if not isinstance(value, list):
                         logging.error(f"Parameter '{parameter}' has incorrect type. Expected list, got {type(value).__name__}.")
                         is_valid = False
                         continue

                # Range validation
                # Range means two different things by type: magnitude for
                # numbers, length for strings in the branch below, and
                # nothing at all for booleans and lists, whose min and max in
                # a rule are read and then silently ignored. A rule writer
                # who set a maximum list length gets no error and no check.
                if data_type in ('integer', 'float'):
                    # The bounds in a rule are never checked themselves. A
                    # minimum written as text in the rules file raises on this
                    # comparison, is caught by the handler around the rule, and
                    # surfaces as a generic error for that parameter, and a rule
                    # whose minimum is above its maximum fails every value while
                    # looking like two ordinary range findings.
                    if min_value is not None and value < min_value:
                        logging.error(f"Parameter '{parameter}' is out of range. Value {value} is less than minimum {min_value}.")
                        is_valid = False
                    if max_value is not None and value > max_value:
                        logging.error(f"Parameter '{parameter}' is out of range. Value {value} is greater than maximum {max_value}.")
                        is_valid = False
                elif data_type == 'string':
                    # For a string rule, min and max are length bounds.
                    if min_value is not None and len(value) < min_value:
                        logging.error(f"Parameter '{parameter}' is out of range. Length {len(value)} is less than minimum length {min_value}.")
                        is_valid = False
                    if max_value is not None and len(value) > max_value:
                        logging.error(f"Parameter '{parameter}' is out of range. Length {len(value)} is greater than maximum length {max_value}.")
                        is_valid = False
            except Exception as e:
                logging.error(f"Error validating parameter '{parameter}': {e}")
                is_valid = False

        return is_valid


def setup_argparse():
    """
    Sets up the argument parser for the command line interface.

    Returns:
        argparse.ArgumentParser: The configured argument parser.
    """
    parser = argparse.ArgumentParser(description='Enforces value ranges and types for configuration parameters.')
    parser.add_argument('-c', '--config', dest='config_file', type=str, required=True,
                        help='Path to the configuration file (JSON or YAML).')
    parser.add_argument('-r', '--rules', dest='rules_file', type=str, required=True,
                        help='Path to the rules file (JSON).')
    return parser


def main():
    """
    Main function to execute the configuration validation.
    """
    parser = setup_argparse()
    args = parser.parse_args()

    # Input validation: check file existence.
    if not os.path.exists(args.config_file):
        logging.error(f"Config file not found: {args.config_file}")
        sys.exit(1)

    if not os.path.exists(args.rules_file):
        logging.error(f"Rules file not found: {args.rules_file}")
        sys.exit(1)

    checker = ConfigValueRangeChecker(args.config_file, args.rules_file)

    if not checker.load_config():
        sys.exit(1)

    if not checker.load_rules():
        sys.exit(1)

    if checker.validate_config():
        logging.info("Configuration is valid.")
        sys.exit(0)  # Exit with success code if valid
    else:
        logging.error("Configuration is invalid.")
        sys.exit(1)  # Exit with error code if invalid


if __name__ == "__main__":
    main()

"""
Usage Examples:

1.  Validate a JSON configuration file against a JSON rules file:
    ```bash
    python misconfig_checker.py -c config.json -r rules.json
    ```

2.  Validate a YAML configuration file against a JSON rules file:
    ```bash
    python misconfig_checker.py -c config.yaml -r rules.json
    ```

Example config.json:
```json
{
  "port": 8080,
  "max_connections": 1000,
  "enabled": true,
  "name": "MyServer"
}
```

Example config.yaml:
```yaml
port: 8080
max_connections: 1000
enabled: true
name: "MyServer"
```

Example rules.json:
```json
[
  {
    "parameter": "port",
    "type": "integer",
    "min": 1024,
    "max": 65535
  },
  {
    "parameter": "max_connections",
    "type": "integer",
    "min": 100,
    "max": 5000
  },
  {
    "parameter": "enabled",
    "type": "boolean"
  },
  {
    "parameter": "name",
    "type": "string"
  }
]
```

Offensive Tool Steps:

1. Fuzzing Configuration Values: This tool can be adapted to fuzz the configuration values. By generating a large number of configuration files with values outside of the defined ranges (or with incorrect data types), you can test the application's error handling and resilience.
2. Rule Set Manipulation:  An attacker could attempt to manipulate the rules file used by the tool, either to disable certain checks or to insert rules that always pass, thus masking misconfigurations.
3. Information Leakage: The tool's logging or error messages may inadvertently reveal sensitive information about the system or application being checked.
4. Denial-of-Service: Repeatedly running the tool with large or complex configurations could potentially exhaust resources.
"""