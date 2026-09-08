"""opendeck_broker — local broker for the OpenCode-dedicated Stream Deck Mini.

Option A from docs/streamdeck-opencode-research.md: one local broker owns the
six slots, receives actual OpenCode state, and routes presses to a Windows
focus adapter. The Mini is controlled directly over HID after the individual
device is disabled in the Elgato app.
"""

__version__ = "0.1.0"
