# Case 05 — Mixed (partial template + hand-positioned content)

**Input.** `input.pptx` — 5 layouts with IR-intent names; 4 slides, half using named layouts, half on Blank with hand-positioned text boxes.

**Represents.** The common real-world hybrid: someone started with a template but went off-script on some slides.

**Tests.** Does the classifier route to `mixed`? Can the system give the user useful information?

**Pipeline.** Classifier → (user choice) Extractor or Synthesizer → Validator → Renderer.
