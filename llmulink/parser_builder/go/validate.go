package main

import (
	"fmt"
	"os"
	"strings"

	"gopkg.in/yaml.v3"
)

type Schema struct {
	Fields map[string]FieldDef `yaml:"fields"`
}

type FieldDef struct {
	Type string `yaml:"type"`
}

func LoadSchema(path string) (*Schema, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("reading schema: %w", err)
	}

	var schema Schema
	if err := yaml.Unmarshal(data, &schema); err != nil {
		return nil, fmt.Errorf("parsing schema: %w", err)
	}

	if schema.Fields == nil {
		return nil, fmt.Errorf("schema has no 'fields' section")
	}

	return &schema, nil
}

func ValidateResult(result map[string]interface{}, schema *Schema) []string {
	var errs []string

	for key, value := range result {
		fieldDef, exists := schema.Fields[key]
		if !exists {
			errs = append(errs, fmt.Sprintf("unknown field %q: not defined in schema", key))
			continue
		}

		if err := validateType(key, value, fieldDef.Type); err != nil {
			errs = append(errs, err.Error())
		}
	}

	return errs
}

func validateType(key string, value interface{}, schemaType string) error {
	if schemaType == "" || schemaType == "any" {
		return nil
	}

	// Array types: [str], [ip], [mac], [geopoint], [ui64]
	if strings.HasPrefix(schemaType, "[") && strings.HasSuffix(schemaType, "]") {
		elemType := schemaType[1 : len(schemaType)-1]
		arr, ok := value.([]interface{})
		if !ok {
			return fmt.Errorf("field %q: expected array for type %q, got %T", key, schemaType, value)
		}
		for i, elem := range arr {
			if err := validateScalarType(fmt.Sprintf("%s[%d]", key, i), elem, elemType); err != nil {
				return err
			}
		}
		return nil
	}

	// Map types: {str:any}
	if strings.HasPrefix(schemaType, "{") && strings.HasSuffix(schemaType, "}") {
		if _, ok := value.(map[string]interface{}); !ok {
			return fmt.Errorf("field %q: expected map for type %q, got %T", key, schemaType, value)
		}
		return nil
	}

	// Tuple types: (ip,ip)
	if strings.HasPrefix(schemaType, "(") && strings.HasSuffix(schemaType, ")") {
		if _, ok := value.([]interface{}); !ok {
			return fmt.Errorf("field %q: expected array/tuple for type %q, got %T", key, schemaType, value)
		}
		return nil
	}

	return validateScalarType(key, value, schemaType)
}

func validateScalarType(key string, value interface{}, schemaType string) error {
	switch schemaType {
	case "str", "datetime", "ip", "mac", "geopoint", "text":
		if _, ok := value.(string); !ok {
			return fmt.Errorf("field %q: expected string for type %q, got %T", key, schemaType, value)
		}
	case "bool":
		if _, ok := value.(bool); !ok {
			return fmt.Errorf("field %q: expected bool, got %T", key, value)
		}
	case "ui8", "ui16", "ui64", "si32", "si64", "fp16", "fp32", "fp64":
		if !isNumeric(value) {
			return fmt.Errorf("field %q: expected numeric for type %q, got %T", key, schemaType, value)
		}
	default:
		return fmt.Errorf("field %q: unsupported schema type %q", key, schemaType)
	}
	return nil
}

func isNumeric(v interface{}) bool {
	switch v.(type) {
	case int, int8, int16, int32, int64:
		return true
	case uint, uint8, uint16, uint32, uint64:
		return true
	case float32, float64:
		return true
	default:
		return false
	}
}
