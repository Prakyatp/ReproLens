You are reading one figure from a scientific paper, to find information that a
researcher would need in order to reproduce the work and that may appear nowhere
in the paper's text.

Report only what is legibly printed or drawn in this image. If you cannot read
something, leave it out.

Do not infer, complete or correct anything:

- An accession you cannot read character by character is not an accession. Do
  not reconstruct one from context, and do not repair one that looks truncated
  or malformed.
- A tool you recognise but cannot actually see named in the image does not
  belong in `tools_named`.
- A version number must be printed in the image. Do not supply the version you
  believe was used.
- Return an empty list rather than a plausible value. An empty list is a useful,
  correct answer. A plausible invention is worse than nothing here, because
  downstream it is indistinguishable from a real reading.

For `workflow_steps`, follow the arrows and give the stages in the order the
data moves through them, as short labels, e.g.
`["FASTQ", "STAR", "featureCounts", "DESeq2"]`.

List each distinct item once. A figure may show the same label many times -- one
box repeated across panels, one axis shared by subplots -- and it is still one
entry. Keep every list short: report the items that matter for reproducing the
work, not a transcription of the image.

The figure's caption, for context only -- do not report values that appear in
the caption but not in the image:

{caption}
