---
title: "GPU sharing via Timeslicing in Kubernetes"
date: 2026-10-04
description: "brother can you spare some GPU cycles?"
tags: [writeup, GPUs, low-level]
---

![GPU-Time-Slicing-Meme](/img/GPU-time-slicing-kubernetes.png){ width="1000" }

During my time at IBM, I've had the opportunity to work on improving the performance of our self-hosted models running on our GPU clusters, and as usual when I dive into a new project, I go down a lot of rabbit holes... One of these being GPU time-slicing.

Your home PC likely has an NVIDIA GPU that gets requested by your operating system and drivers to run graphics-intensive applications, but what if you want to share your GPU with another computer?

This probably sounds weird, but it's really important to be able to do this, especially in the world of AI inference.

Having a data-center-grade GPU on your Kubernetes cluster and only accepting requests from a single pod is likely causing a ton of starvation, especially if that pod is not continuously using the GPU.

I actually found out this was a problem at work when we wanted to integrate more services with the GPU, so I decided it was time to dig into the NVIDIA docs to see if there was a solution. And there was: NVIDIA GPU time-slicing.

## How it works

The NVIDIA GPU Operator running on Kubernetes configures the NVIDIA Kubernetes Device Plugin to oversubscribe resources by essentially advertising a set number of virtual replicas for a single GPU.

When multiple pods are assigned to these virtual replicas, the underlying NVIDIA driver and hardware scheduler handle context switching and time-multiplexing between the active CUDA contexts.

The GPU can then run work from one context, switch to another context, run that work, and continue doing this for all the pods sharing the GPU.

The GPU itself is not being physically divided into multiple GPUs, by the way. Kubernetes is just allowing multiple workloads to be scheduled against the same physical device, while the GPU handles sharing execution time between them.

## There's always a catch

As you might have noticed though, there are some tradeoffs to this approach.

There will be some slowdowns due to things like context switching. When switching between CUDA contexts, the GPU needs to save and restore the state associated with those contexts, and some of that state has to be moved through slower levels of the GPU memory hierarchy like global memory.

This means that context switching is not free. Depending on the architecture and the amount of state that needs to be saved and restored, the overhead can be on the order of hundreds of clock cycles.

With this, you likely wouldn't be using time-slicing with a huge number of virtual replicas, or at least you would want to benchmark the workload to determine how much contention and context-switching overhead you're willing to accept for your applications.

## There's also another catch

But there's one caveat of this approach that is a bit annoying to me though, and I'm not sure if there's a way around it that wouldn't cause an even worse performance hit... Observability.

Because multiple pods are using the same GPU, performing observability on the speed of workloads for each pod would require knowing which GPU work is coming from which pod.

For example, if the GPU is reporting 90% utilization, that doesn't necessarily tell you:
- Which pod is responsible for that utilization
- How much GPU time each pod is receiving
- Or whether one workload is being slowed down by another workload sharing the same device

Ideally, you'd want to be able to attribute GPU activity back to the Kubernetes workload that caused it, but that becomes much more complicated when multiple pods are sharing the same physical GPU and their CUDA contexts are being scheduled over time.

I would guess instrumenting observability to this level would cause even more latency and overhead, which I'm not super certain is worth it and I'd guess is why it remains unimplemented.

### Other approaches

There are also other NVIDIA technologies that are relevant to GPU sharing, such as MPS and MIG.

MPS, or Multi-Process Service, allows multiple CUDA processes to share a GPU, while MIG, or Multi-Instance GPU, can partition supported NVIDIA GPUs into separate hardware instances with dedicated resources.

These approaches have different tradeoffs and are useful for different workloads, so time-slicing isn't necessarily the right solution for every GPU-sharing problem.

But yea, anyways, if your issue is that you need multiple distinct services to use the same hardware and that cost is negligible to you, this is the perfect solution!

## Terminology

### GPU oversubscription

GPU oversubscription is when more workloads are scheduled against a GPU resource than there are physical GPUs available.

With NVIDIA GPU time-slicing, the Kubernetes Device Plugin can advertise multiple logical replicas for a single physical GPU. Kubernetes can then schedule multiple pods against those replicas even though they are ultimately sharing the same physical device.

### CUDA context

A CUDA context is the execution environment associated with a CUDA application on a GPU. It contains state required for the GPU to execute work on behalf of that application.

Multiple CUDA contexts can exist on the same GPU, allowing work from different CUDA applications to be scheduled on the same physical device.

### Context switching

Context switching is the process of switching the GPU from executing work associated with one CUDA context to executing work associated with another.

The GPU needs to preserve the state associated with the current context and restore the state required by the next context. This introduces overhead because some of that state needs to be moved through the GPU memory hierarchy.

### Time-multiplexing

Time-multiplexing is a method of sharing the same resource between multiple workloads by giving each workload access to the resource at different points in time.

You can kind of think of it like two people taking turns speaking one word of a sentence at a time, then being able to reconstruct the sentences after listening.

With GPU time-slicing, different CUDA contexts take turns getting execution time on the same physical GPU.

### CUDA kernel

A CUDA kernel is a function that is executed on the GPU. When a CUDA application launches a kernel, it is requesting that the GPU execute that function across a set of GPU threads.

This is separate from the operating-system concept of a kernel, despite both using the same terminology.

### GPU hardware scheduler

The GPU hardware scheduler is responsible for scheduling work for execution on the GPU. The exact implementation and behavior depends on the GPU architecture, but it is part of the mechanism that allows work from different contexts to share the physical GPU.

### MPS

MPS, or Multi-Process Service, is an NVIDIA technology that allows multiple CUDA processes to share a GPU through an MPS server.

It is another mechanism for GPU sharing, but it has different behavior and use cases from Kubernetes GPU time-slicing.

### MIG

MIG, or Multi-Instance GPU, is an NVIDIA technology available on supported GPUs that allows a physical GPU to be partitioned into multiple GPU instances.

Unlike time-slicing, which primarily shares execution time on the same physical GPU, MIG partitions supported hardware resources into separate instances with dedicated resources and stronger isolation between workloads.

### Observability

Observability is the ability to understand what is happening inside a system using the information that the system exposes, such as metrics, logs, and traces.

In this context, the interesting problem is being able to attribute GPU activity and performance back to an individual Kubernetes workload when multiple workloads are sharing the same physical GPU.
