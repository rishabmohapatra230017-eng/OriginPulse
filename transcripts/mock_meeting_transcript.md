# Mock Meeting Transcript: Fetal Anomaly Model Deployment Sync

Sarah: Thanks for making the time, both of you. I know clinic schedules are all over the place this week. The goal for this sync is pretty narrow: how did the fetal anomaly detection deployment behave over the first forty-eight hours, what do we need to fix before the broader pilot, and what needs to be communicated to the clinical partners.

Alex: Yep. From the engineering side, the deployment itself was clean. The new model is live behind the pilot flag, inference latency is in a better place than we expected, and we have telemetry from all three test sites. The messy bit is not the model server. It is the scan ingestion pipeline.

Jamie: When you say messy, do you mean missing studies, delayed studies, or the usual DICOM metadata weirdness?

Alex: A little of the usual metadata weirdness, but there is also a real bug. On Tuesday evening, about 11% of studies from Westbridge came in without the gestational-age field normalized correctly. The raw tag was present, but our normalization step returned null.

Sarah: Wait, 11% of all scans, or 11% of the Westbridge batch?

Alex: Sorry, yes, 11% of the Westbridge batch. Across all pilot traffic it is closer to 3%. Still not acceptable, because gestational age is one of the inputs for the confidence thresholding.

Jamie: That explains one thing I saw. There were two cases where the anomaly probability looked clinically plausible, but the UI put it into the lower urgency bucket. I was going to ask whether the model changed, but it sounds like the thresholding context was incomplete.

Alex: Exactly. The model output was fine. The downstream risk-banding logic had incomplete context.

Sarah: Okay, so action there is for Alex to check the pipeline bug and confirm whether we need a backfill. Can you get that done by Friday?

Alex: Yes. I can trace the Westbridge cases and patch the normalization rule by Friday. If the fix is bigger than I think, I will at least have a mitigation plan by then.

Jamie: Can we also make sure the affected scans are reprocessed? I do not want the clinical team reviewing screenshots that were generated from bad context.

Alex: Agreed. I will include reprocessing in the same ticket, unless you want that separated.

Sarah: Keep it as one engineering ticket for now, but make the reprocessing step explicit.

Jamie: On the clinical side, I reviewed the first twenty-five flagged studies. The model is catching the obvious ventriculomegaly examples, which is good. The harder cases are abdominal wall findings. It is a bit noisy there. Not terrible, just, you know, the kind of thing where I do not want us overclaiming.

Sarah: Yeah, no overclaiming. For the partner update, I want to say early deployment is stable, we are validating risk-banding behavior, and we are still collecting clinical feedback on the abdominal wall category.

Alex: That sounds accurate.

Jamie: I need more annotation coverage before I can say anything stronger. We have fifty new scans from Northlake that are appropriate for this, but they are not annotated yet. I can coordinate with Dr. Patel's team.

Sarah: What timeline is realistic?

Jamie: If I send the packet today, I think we can get clinical annotation on those fifty scans by next Wednesday. Maybe Thursday if clinic volume gets weird, but I will ask for Wednesday.

Sarah: Great. Jamie owns annotation on the fifty new Northlake scans by next Wednesday.

Jamie: Yes.

Alex: One related thing: the monitoring dashboard currently shows total inference count and average latency, but it does not split by anomaly category. If abdominal wall findings are noisy, we should track that separately.

Sarah: Is that a quick dashboard change or a data model change?

Alex: Mostly dashboard. The category is already in the event payload. I need to add a grouped panel and probably one alert threshold. It is not huge.

Sarah: Can you add that to this sprint?

Alex: I can add the dashboard panel by Monday. The alert threshold may need Jamie's input, because I do not know what level of category-specific drift is clinically meaningful.

Jamie: I can give you a first-pass threshold. It will be a little provisional, but better than nothing.

Sarah: Okay, action item: Alex adds the category-level monitoring panel by Monday, and Jamie gives him a provisional threshold. Jamie, can you send that by end of day tomorrow?

Jamie: Yes, end of day tomorrow works.

Sarah: Perfect.

Jamie: Also, small thing. In the UI, the phrase "suspected anomaly" is showing up next to every highlighted region. That is not how clinicians will read it. For some categories it is fine, but for soft markers it is too strong. We should say "region for review" or something like that.

Sarah: Oh, that is important. I thought we changed that copy last sprint.

Alex: We changed it in the report export. I do not think we changed it in the image viewer overlay.

Sarah: Got it. I will update the sprint board today and add a product copy task. I can draft the new wording and route it to Jamie before it goes to engineering.

Jamie: Please do. I would avoid "suspected" unless there is a confirmed model threshold and clinical context.

Sarah: Noted. I will update the sprint board today and tag the UI copy item as needing clinical review.

Alex: On the deployment health side, there were no elevated error rates. Peak latency was 1.8 seconds, p95 stayed under 900 milliseconds after the cache warmed up, and GPU utilization was boring, which is my favorite kind of metric.

Sarah: Boring is good.

Jamie: Very good.

Sarah: Any patient safety concern from what we saw so far?

Jamie: Nothing that would make me stop the pilot, as long as the risk-banding bug is addressed and the UI language gets softened. My concern is interpretation, not raw model behavior.

Alex: Same from engineering. I do want to add one temporary guardrail: if gestational age is missing after normalization, we should mark the study as needing review instead of assigning a lower urgency bucket. That way missing context fails cautious.

Sarah: That makes sense. Is that part of the Friday pipeline fix?

Alex: It can be. I will add it as acceptance criteria.

Sarah: Good. Anything else before we wrap?

Jamie: Just one ambiguous thing. The partner team asked whether the "pilot metrics" include scans that failed preprocessing. I told them I would check, but I am not sure who owns the answer.

Alex: I can answer the technical part. Failed preprocessing scans are in the ingestion dashboard but not in the model-performance denominator.

Sarah: I should probably own the partner-facing explanation. Alex, can you send me the technical definition, and I will turn it into language for the partner update?

Alex: Sure. I can send that by tomorrow morning.

Sarah: Great. Then I will send the partner update by end of day tomorrow after I get Alex's definition and Jamie's wording feedback.

Jamie: Works for me.

Sarah: Quick recap: Alex owns the Westbridge pipeline bug and cautious fallback by Friday, Alex adds category-level monitoring by Monday, Jamie coordinates annotation on fifty Northlake scans by next Wednesday, Jamie sends provisional drift threshold guidance by tomorrow, Sarah updates the sprint board and UI copy task today, and Sarah sends the partner update tomorrow after getting inputs. Anything I missed?

Alex: That covers engineering.

Jamie: That covers clinical.

Sarah: Great. Thanks both. I will put the notes in the project channel after this.
