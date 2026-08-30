package telemetry

import "strconv"

// itoa is a tiny int->string helper (used by the hand-rolled metrics).
func itoa(n int) string { return strconv.Itoa(n) }
