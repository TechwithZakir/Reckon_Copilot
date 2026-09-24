const STRUCTURED_KEYS = new Set([
  "title",
  "heading",
  "summary",
  "description",
  "message",
  "next_areas",
  "visible_kpi_cards",
  "kpi_cards",
  "charts",
  "filters",
]);

const SECTION_LABELS = {
  next_areas: "Next areas",
  visible_kpi_cards: "Key figures",
  kpi_cards: "Key figures",
  charts: "Charts",
  filters: "Filters in scope",
};

export function formatAnswer(raw) {
  const text = String(raw || "").trim();
  const parsed = parseStructuredAnswer(text);
  if (!isPlainObject(parsed)) {
    return { kind: "text", plainText: text, sections: [], details: [] };
  }

  const title = firstText(parsed.title, parsed.heading) || "Copilot summary";
  const summary = firstText(parsed.summary, parsed.description, parsed.message);
  const details = [];
  const sections = [];

  for (const [key, value] of Object.entries(parsed)) {
    if (STRUCTURED_KEYS.has(key) || value === null || value === undefined) continue;
    if (isScalar(value)) {
      details.push({ label: humanizeKey(key), value: displayValue(value) });
    } else if (Array.isArray(value)) {
      sections.push({ title: humanizeKey(key), items: value.map(formatItem).filter(Boolean) });
    } else if (isPlainObject(value)) {
      sections.push({ title: humanizeKey(key), items: [formatItem(value)].filter(Boolean) });
    }
  }

  for (const key of ["next_areas", "visible_kpi_cards", "kpi_cards", "charts", "filters"]) {
    if (!(key in parsed)) continue;
    const value = parsed[key];
    const items = Array.isArray(value) ? value.map(formatItem).filter(Boolean) : [formatItem(value)].filter(Boolean);
    if (items.length) sections.push({ title: SECTION_LABELS[key] || humanizeKey(key), items });
  }

  const plainText = buildPlainText(title, summary, details, sections);
  return { kind: "structured", title, summary, details, sections, plainText };
}

export function parseStructuredAnswer(raw) {
  const text = stripCodeFence(String(raw || "").trim());
  if (!text || !/^[\[{]/.test(text)) return null;
  try {
    return JSON.parse(text);
  } catch {
    try {
      return new LiteralParser(text).parse();
    } catch {
      return null;
    }
  }
}

export function humanizeKey(key) {
  return String(key || "")
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function buildPlainText(title, summary, details, sections) {
  const lines = [title];
  if (summary) lines.push(summary);
  for (const detail of details) lines.push(`${detail.label}: ${detail.value}`);
  for (const section of sections) {
    lines.push("", section.title);
    for (const item of section.items) lines.push(`- ${item}`);
  }
  return lines.join("\n");
}

function formatItem(value) {
  if (isScalar(value)) return displayValue(value);
  if (Array.isArray(value)) return value.map(formatItem).filter(Boolean).join(", ");
  if (!isPlainObject(value)) return "";

  const preferred = firstText(value.label, value.title, value.name, value.key);
  const preferredValueKey = ["value", "data", "status", "amount", "count"]
    .find((key) => key in value);
  if (preferred && preferredValueKey) {
    return `${preferred}: ${displayValue(value[preferredValueKey])}`;
  }
  const entries = Object.entries(value)
    .filter(([key]) => !["label", "title", "name", "key"].includes(key))
    .map(([key, item]) => `${humanizeKey(key)}: ${displayValue(item)}`)
    .filter(Boolean);
  if (preferred && !entries.length) return preferred;
  if (preferred) return `${preferred}: ${entries.join(" · ")}`;
  return entries.join(" · ");
}

function displayValue(value) {
  if (value === null || value === undefined || value === "") return "Unavailable";
  if (Array.isArray(value)) return value.map(displayValue).join(", ");
  if (isPlainObject(value)) return formatItem(value);
  if (typeof value === "boolean") return value ? "Yes" : "No";
  return String(value);
}

function firstText(...values) {
  return values.find((value) => value !== null && value !== undefined && isScalar(value) && String(value).trim())
    ? String(values.find((value) => value !== null && value !== undefined && isScalar(value) && String(value).trim())).trim()
    : "";
}

function isScalar(value) {
  return value === null || ["string", "number", "boolean"].includes(typeof value);
}

function isPlainObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function stripCodeFence(text) {
  if (!text.startsWith("```")) return text;
  return text
    .replace(/^```(?:json|javascript|js)?\s*/i, "")
    .replace(/\s*```$/, "")
    .trim();
}

class LiteralParser {
  constructor(text) {
    this.text = text;
    this.index = 0;
  }

  parse() {
    const value = this.parseValue();
    this.skipWhitespace();
    if (this.index !== this.text.length) throw new Error("Unexpected input");
    return value;
  }

  parseValue() {
    this.skipWhitespace();
    const char = this.text[this.index];
    if (char === "{") return this.parseObject();
    if (char === "[") return this.parseArray();
    if (char === "'" || char === '"') return this.parseString();
    if (char === "-" || /\d/.test(char || "")) return this.parseNumber();
    return this.parseIdentifierValue();
  }

  parseObject() {
    const result = {};
    this.index += 1;
    this.skipWhitespace();
    if (this.text[this.index] === "}") {
      this.index += 1;
      return result;
    }
    while (this.index < this.text.length) {
      this.skipWhitespace();
      const key = this.text[this.index] === "'" || this.text[this.index] === '"'
        ? this.parseString()
        : this.parseIdentifier();
      if (["__proto__", "constructor", "prototype"].includes(key)) {
        throw new Error("Unsafe object key");
      }
      this.skipWhitespace();
      if (this.text[this.index] !== ":") throw new Error("Expected object separator");
      this.index += 1;
      result[key] = this.parseValue();
      this.skipWhitespace();
      if (this.text[this.index] === "}") {
        this.index += 1;
        return result;
      }
      if (this.text[this.index] !== ",") throw new Error("Expected object delimiter");
      this.index += 1;
    }
    throw new Error("Unclosed object");
  }

  parseArray() {
    const result = [];
    this.index += 1;
    this.skipWhitespace();
    if (this.text[this.index] === "]") {
      this.index += 1;
      return result;
    }
    while (this.index < this.text.length) {
      result.push(this.parseValue());
      this.skipWhitespace();
      if (this.text[this.index] === "]") {
        this.index += 1;
        return result;
      }
      if (this.text[this.index] !== ",") throw new Error("Expected array delimiter");
      this.index += 1;
    }
    throw new Error("Unclosed array");
  }

  parseString() {
    const quote = this.text[this.index++];
    let result = "";
    while (this.index < this.text.length) {
      const char = this.text[this.index++];
      if (char === quote) return result;
      if (char !== "\\") {
        result += char;
        continue;
      }
      const escaped = this.text[this.index++];
      const escapes = { n: "\n", r: "\r", t: "\t", b: "\b", f: "\f", "\\": "\\", "'": "'", '"': '"' };
      if (escaped === "u") {
        const code = this.text.slice(this.index, this.index + 4);
        if (!/^[0-9a-f]{4}$/i.test(code)) throw new Error("Invalid unicode escape");
        result += String.fromCharCode(parseInt(code, 16));
        this.index += 4;
      } else {
        result += escapes[escaped] ?? escaped;
      }
    }
    throw new Error("Unclosed string");
  }

  parseNumber() {
    const match = this.text.slice(this.index).match(/^-?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?/);
    if (!match) throw new Error("Invalid number");
    this.index += match[0].length;
    return Number(match[0]);
  }

  parseIdentifier() {
    const match = this.text.slice(this.index).match(/^[A-Za-z_$][\w$-]*/);
    if (!match) throw new Error("Invalid identifier");
    this.index += match[0].length;
    return match[0];
  }

  parseIdentifierValue() {
    const identifier = this.parseIdentifier();
    if (["null", "None"].includes(identifier)) return null;
    if (["true", "True"].includes(identifier)) return true;
    if (["false", "False"].includes(identifier)) return false;
    return identifier;
  }

  skipWhitespace() {
    while (/\s/.test(this.text[this.index] || "")) this.index += 1;
  }
}
