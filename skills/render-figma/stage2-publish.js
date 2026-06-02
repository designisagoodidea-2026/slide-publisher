// Stage 2 publish script for render-figma.
//
// Executed via the Anthropic-hosted Figma MCP (`use_figma`) against the
// user's Figma Slides file. Clones layout-template slides identified by
// the profile's layout_map, then populates them with IR content.
//
// Input (injected by the skill orchestrator before sending to use_figma):
//   - LAYOUT_MAP: { intent: template_slide_node_id, ... }
//   - FALLBACK_CHAIN: { intent: [fallback_intent_1, ...], ... }
//   - IR_SLIDES: [ { layout_intent, title, body, speaker_notes? }, ... ]
//
// Output:
//   JSON envelope: { created, losses, output_row_id, file_url,
//                    slides: [ {slide_index, intent, template_id, slide_id} ],
//                    loss_manifest: [ {slide_index, kind, field, reason} ] }
//
// Conforms to FIGMA-PLUGIN-API-RULES.md:
//   Rule 1: shallow walk only (clone.children iteration, no findAll).
//   Rule 4: pre-load every font discovered on used templates BEFORE setCharacters.
//   Rule 5: capture typography → setCharacters → restore typography (font, size, fills, align).
//   Rule 6: identify nodes by `.name` ("TITLE", "BODY") on the cloned template.
//   Rule 8: single use_figma invocation handles all clone + populate operations.
//
// Layout fallback: if an intent has no direct template, walks
// FALLBACK_CHAIN[intent] in order. If still none, slide is logged as DROPPED.

// === INJECTED CONFIG ===========================================
const layoutMap = /* {{ LAYOUT_MAP_JSON }} */ {};
const fallbackChain = /* {{ FALLBACK_CHAIN_JSON }} */ {};
const irSlides = /* {{ IR_SLIDES_JSON }} */ [];
// ===============================================================

function resolveTemplate(intent) {
  if (layoutMap[intent]) return layoutMap[intent];
  for (const fb of (fallbackChain[intent] || [])) {
    if (layoutMap[fb]) return layoutMap[fb];
  }
  return null;
}

const cp = figma.currentPage;
const grid = cp.children.find(c => c.type === "SLIDE_GRID");
if (!grid) return JSON.stringify({error: "no SLIDE_GRID on current page"});

// ---- Rule 4: pre-load fonts found on every template we'll use ----
const fontsNeeded = new Set();
const usedTemplateIds = new Set();
for (const ir of irSlides) {
  const tid = resolveTemplate(ir.layout_intent);
  if (tid) usedTemplateIds.add(tid);
}
for (const tid of usedTemplateIds) {
  const tpl = figma.getNodeById(tid);
  if (tpl && tpl.children) {
    for (const c of tpl.children) {
      if (c.type === "TEXT" && c.fontName) {
        fontsNeeded.add(JSON.stringify(c.fontName));
      }
    }
  }
}
for (const fnJson of fontsNeeded) {
  await figma.loadFontAsync(JSON.parse(fnJson));
}

// ---- Create a fresh render row (Rule 8: single batch) ----
const renderRow = figma.createSlideRow();
grid.appendChild(renderRow);
renderRow.setSharedPluginData("slide_publisher", "row_kind", "render_output");
renderRow.setSharedPluginData("slide_publisher", "rendered_at", new Date().toISOString());

const created = [];
const losses = [];

function setWithStyleRestore(node, text) {
  if (!node || text == null) return false;
  // Rule 5: capture typography before setCharacters resets it
  const fn = node.fontName;
  const fs = node.fontSize;
  const align = node.textAlignHorizontal;
  const fills = node.fills;
  const autoResize = node.textAutoResize;
  node.characters = String(text);
  try { node.fontName = fn; } catch (e) {}
  try { node.fontSize = fs; } catch (e) {}
  try { node.textAlignHorizontal = align; } catch (e) {}
  try { node.fills = fills; } catch (e) {}
  try { node.textAutoResize = autoResize; } catch (e) {}
  return true;
}

for (let i = 0; i < irSlides.length; i++) {
  const ir = irSlides[i];
  const templateId = resolveTemplate(ir.layout_intent);
  if (!templateId) {
    losses.push({slide_index: i, kind: "DROPPED", reason: `no template for '${ir.layout_intent}' (no fallback found)`});
    continue;
  }
  const template = figma.getNodeById(templateId);
  if (!template) {
    losses.push({slide_index: i, kind: "DROPPED", reason: `template node ${templateId} not in file`});
    continue;
  }
  const clone = template.clone();
  renderRow.appendChild(clone);

  // Rule 1 + Rule 6: shallow walk by name
  let titleNode = null, bodyNode = null;
  for (const child of clone.children) {
    if (child.type === "TEXT") {
      if (child.name === "TITLE") titleNode = child;
      else if (child.name === "BODY") bodyNode = child;
    }
    if (child.name === "INTENT") child.remove();  // strip metadata
  }

  const titleOk = setWithStyleRestore(titleNode, ir.title);
  const bodyOk  = setWithStyleRestore(bodyNode,  ir.body);

  clone.setSharedPluginData("slide_publisher", "rendered_from_intent", ir.layout_intent);
  clone.setSharedPluginData("slide_publisher", "ir_index", String(i));

  if (ir.speaker_notes && typeof clone.speakerNotes !== "undefined") {
    try { clone.speakerNotes = ir.speaker_notes; } catch (e) {}
  }

  if (!titleOk) losses.push({slide_index: i, kind: "DROPPED", field: "title", reason: "no TITLE node in template clone"});
  if (!bodyOk && ir.body) losses.push({slide_index: i, kind: "LOSSY", field: "body", reason: "no BODY node — body content dropped"});

  created.push({slide_index: i, intent: ir.layout_intent, template_id: templateId, slide_id: clone.id});
}

return JSON.stringify({
  created: created.length,
  losses: losses.length,
  output_row_id: renderRow.id,
  file_url: `https://www.figma.com/slides/${figma.fileKey || ""}?node-id=${renderRow.id.replace(/:/g,"-")}`,
  slides: created,
  loss_manifest: losses,
});
