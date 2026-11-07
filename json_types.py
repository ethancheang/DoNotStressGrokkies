"""Type aliases for the JSON-shaped check-in data shared by every layer.

A check-in moves through the app as a JSON object: it arrives from the
browser, is sent to Gemini, and is saved to the records file. These aliases
name that shape so type hints never fall back to Any.
"""

type JSONValue = (
    str | int | float | bool | None | list[JSONValue] | dict[str, JSONValue]
)
type JSONObject = dict[str, JSONValue]
