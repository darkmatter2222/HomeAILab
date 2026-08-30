package discovery

import (
	"encoding/json"

	"gopkg.in/yaml.v3"

	"llm-router/internal/manifest"
)

func yamlUnmarshal(b []byte, v any) error { return yaml.Unmarshal(b, v) }

func jsonUnmarshal(b []byte, v any) error { return json.Unmarshal(b, v) }

var _ = manifest.Manifest{}
