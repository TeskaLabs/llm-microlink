package main

import (
	"encoding/json"
	"fmt"
	"os"
	"sort"
)

func main() {
	if len(os.Args) < 2 {
		fmt.Fprintln(os.Stderr, "Usage: parse <logfile> <schemafile>")
		os.Exit(1)
	}

	schema, err := LoadSchema(os.Args[2])
	if err != nil {
		fmt.Fprintf(os.Stderr, "Failed to load schema: %v\n", err)
		os.Exit(1)
	}

	log, err := os.ReadFile(os.Args[1])
	if err != nil {
		fmt.Fprintf(os.Stderr, "Failed to read file: %v\n", err)
		os.Exit(1)
	}

	result := Parse(log)
	if result == nil || (len(result) == 0) {
		fmt.Println("Parsing failed: result is empty")
		os.Exit(1)
	}

	errs := ValidateResult(result, schema)
	if len(errs) > 0 {
		sort.Strings(errs)
		fmt.Fprintf(os.Stdout, "Schema validation found %d issue(s):\n", len(errs))
		for _, e := range errs {
			fmt.Fprintf(os.Stdout, "  - %s\n", e)
		}
		fmt.Println("")
	}

	jsonBytes, err := json.MarshalIndent(result, "", "\t")
	if err != nil {
		fmt.Println("Failed to marshal result to JSON: %v\n", err)
		os.Exit(1)
	}

	fmt.Println("```json")
	fmt.Println(string(jsonBytes))
	fmt.Println("```")

	if len(errs) > 0 {
		os.Exit(1)
	}

	os.Exit(0)
}
