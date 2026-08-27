---
title: "Kernel Harbor -- An EDR with LLM analysis of kernel events"
date: 2026-08-01
description: ""
tags: [writeup, Go, C, low-level, cybersecurity]
---

Something I'd been toying around with recently is the idea of AI threat detection and response, so I decided to build my own Endpoint Detection and Response system using kernel level event monitoring from my favorite vendors (Falco / Cilium) and implemented a RAG based analysis of the telemetry that comes in.

## Rounding up the Avengers lol

This project was inspired by my security work at IBM where I'd been working on anti-abuse systems for Kubernetes, particularly the use of eBPF.

I posted about my idea of starting a project using that technology on LinkedIn, and to my surprise a bunch of people wanted to join in on the fun!

Unfortunately I wasn't able to let absolutely everyone who wanted to participate as a big BIG team would be too unwieldy, so this was the team I ended up forming:

- AI Security Software Engineer @ Trend AI -- Kien Do
- GPU Programmer Intern @ AMD -- John Tyler
- Incident Response Intern @ KPMG -- Mehar Klair
- Infra/Security Software Engineer Intern @ IBM -- Yours Truly

Couldn't have asked for a better team :)

## There are layers to this

One thing I didn't want to do though is attach an LLM directly to every single event that comes in. That would be a logistical nightmare costing a zillion dollars in inference costs.

There are moments to use AI and moments when not to.

Sort of like how there's a fast and slow path when reacting to something. If it looks like a duck, quacks like a duck, then it's probably a duck and we can choose the fast path. But if it only quacks like a duck, well now we're not sure and go with a slow path.

I'll let you fill in the blanks as to what the path means for the duck. Depends if you're hungry or not.

But anyways, there are a couple ways we can do a layered approach.

Initially I was thinking of two layers.

- One for heuristic rules that trigger responses immediately for things like Regex-based patterns for obviously malicious commands
- And another for LLM analysis for when we want to search our database via RAG for semantically similar past events (and check if it matches as malicious)

But there was one flaw with this approach.

It doesn't maintain temporal context.

We wouldn't be able to understand a multi-step attack chain occurring within a 30-second window for example if we don't keep track of chained events.

That said, I modified the plan to have a 3-layer approach with:

- Heuristic Rules (Immediate)
- Correlation Engine (Immediate)
- AI/LLM Analysis (Delayed)

## So is it a duck?

Now onto the LLM analysis. This would be the last layer that gets triggered if the previous 

My model of choice, was qwen2.5:1.5b (text generation) with nomic-embed-text (for embeddings). I mainly chose the model because I had a terrible laptop when I started this project LOL. It's likely undersized, but it worked for my initial testing. As for the embeddings, it was fine to use nomic-embed-text over nomic-embed-code since it wasn't really source code, and more of human readable strings that were being fed to it.

The data I wanted this model to do was mainly create behavior summaries based on the events that come in.



## I live for this sh*t

The PR was merged into cilium:main with commit f221631 :)

Something I DIDN'T expect though, was for my fix to be given backport labels because this fix needed to go to every supported release from 1.17 all the way to the latest 1.20!!

![cilium-backport](/img/cilium-backport.png){ width="500" }

That means any clusters running the affected versions will no longer experience this crash-loop on startup :))

## Anddd what did we learn?


Fast paths are dangerous without fallbacks. The original code assumed the pool would always be ready. It wasn't. Always handle the "not ready yet" case gracefully.

Upstream syncs are your friend. The fast path existed for performance, but performance means nothing if the agent crashes. Sometimes you need to take the slower path to ensure correctness.


Exponential backoff is underrated. It's not just for API rate limiting. It's for any situation where you're waiting for a dependency to become available.


Open source is a conversation. The maintainers (shoutout to @gandro) were incredibly helpful throughout the review process. In this PR they were pretty happy with my approach, but certain things regarding maintainability were very useful. Even a nit is worth analyzing why.

![cilium-approach-validation](/img/cilium-approach-validation.png){ width="1000" }

## i'll be back

This was my first contribution to Cilium, one of the world's go-to Kubernetes CNIs, and it won't be my last >:)

Wanna see the code? [PR #47497](https://github.com/cilium/cilium/pull/47497)
