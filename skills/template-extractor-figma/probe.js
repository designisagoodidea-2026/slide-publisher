// Stage 1 extractor probe for template-extractor-figma.
//
// Executed via the Anthropic-hosted Figma MCP (`use_figma`).
// Input:  fileKey of a slide-publisher template (slides tagged with
//         shared plugin data namespace "slide_publisher", key "intent").
// Output: JSON the template_extractor_figma.py adapter consumes —
//         { file_key, slide_templates, color_styles, text_styles }.
//
// Conforms to FIGMA-PLUGIN-API-RULES.md:
//   Rule 1: shallow walk only — never findAll on slides.
//   Rule 2: identify by stable signal — sharedPluginData, not slide.name
//           (Figma Slides auto-renumbers slide.name and drops user-set names).
//   Rule 3: navigate via grid.row.slide.children one level deep.
//   Rule 4: pre-load fonts is not needed for read-only walk.
//   Rule 5: not applicable (no setCharacters here).
//   Rule 6: identify text nodes by their `.name` ("TITLE", "BODY",
//           "IMAGE_PLACEHOLDER") and by sharedPluginData where possible.
//   Rule 7: not applicable (read-only).
//   Rule 8: single use_figma call returns the whole JSON envelope.
//
// Run this with `use_figma` from a Cowork/Claude session. Pipe the returned
// JSON into adapters/template_extractor_figma.py:
//
//   python3 adapters/template_extractor_figma.py --out profile-entry.json < raw.json

const NS = "slide_publisher";
const cp = figma.currentPage;
const grid = cp.children.find(c => c.type === "SLIDE_GRID");
if (!grid) return JSON.stringify({error: "no SLIDE_GRID on current page"});
const row = grid.children.find(c => c.type === "SLIDE_ROW");
if (!row) return JSON.stringify({error: "no SLIDE_ROW in SLIDE_GRID"});

function rgbToHex(c) {
  const t = (n) => Math.round(n * 255).toString(16).padStart(2, "0");
  return ("#" + t(c.r) + t(c.g) + t(c.b)).toUpperCase();
}

function getIntent(slide) {
  // Primary: shared plugin data (stable, machine-readable).
  const fromPluginData = slide.getSharedPluginData(NS, "intent");
  if (fromPluginData) return fromPluginData;
  // Fallback: off-canvas INTENT text node.
  const intentNode = slide.children.find(c => c.type === "TEXT" && c.name === "INTENT");
  if (intentNode && intentNode.characters && intentNode.characters.startsWith("INTENT:")) {
    return intentNode.characters.slice("INTENT:".length).trim();
  }
  return null;
}

const slide_templates = [];
const fontSet = new Set();
const fillSet = new Set();

for (const slide of row.children) {
  if (slide.type !== "SLIDE") continue;
  const intent = getIntent(slide);
  if (!intent) continue;  // skip unidentified slides — extractor reports them as warnings

  const text_nodes = [];
  let titleNode = null, bodyNode = null, imageNode = null;
  for (const child of slide.children) {
    if (child.name === "INTENT") continue;  // skip metadata
    if (child.type === "TEXT") {
      if (child.name === "TITLE") titleNode = child;
      if (child.name === "BODY")  bodyNode  = child;
      const f = child.fontName || {};
      text_nodes.push({
        node_id: child.id, name: child.name,
        characters: child.characters,
        size_pt: child.fontSize,
        family: f.family, style: f.style,
      });
      if (f.family) {
        fontSet.add(JSON.stringify({family: f.family, style: f.style, size_pt: child.fontSize}));
      }
      if (Array.isArray(child.fills)) {
        for (const fill of child.fills) {
          if (fill && fill.type === "SOLID" && fill.color) fillSet.add(rgbToHex(fill.color));
        }
      }
    } else if (child.type === "RECTANGLE" && child.name === "IMAGE_PLACEHOLDER") {
      imageNode = {node_id: child.id, x: child.x, y: child.y, w: child.width, h: child.height};
    }
  }

  slide_templates.push({
    node_id: slide.id,
    intent,
    title_text: intent,
    title_node_id: titleNode ? titleNode.id : null,
    body_node_id:  bodyNode  ? bodyNode.id  : null,
    image_node_id: imageNode ? imageNode.node_id : null,
    text_nodes,
  });
}

const text_styles = [];
for (const entry of fontSet) {
  const p = JSON.parse(entry);
  text_styles.push({
    family: p.family, style: p.style, size_pt: p.size_pt,
    weight: (p.style && /bold/i.test(p.style)) ? 700 : 400,
    name: `${p.family} ${p.style} ${p.size_pt}pt`,
  });
}

const color_styles = [];
for (const hex of fillSet) {
  if (hex === "#000000" || hex === "#FFFFFF") continue;
  color_styles.push({name: hex, hex});
}

return JSON.stringify({
  file_key: figma.fileKey || null,
  extractor_version: "0.2.0-dev",
  slide_templates,
  color_styles,
  text_styles,
});
