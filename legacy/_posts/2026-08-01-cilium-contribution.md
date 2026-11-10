---
title: "Fixing a deadlock in a 24k-star Kubernetes CNI. Here's how I did it."
date: 2026-08-01
description: "what a lovely way to spend the weekend"
tags: [writeup, Go, Kubernetes, Open Source, Networks]
---


![cilium-merged](/img/cilium-merged.jpeg){ width="1000" }

The CNI is Cilium. The deadlock was in multi-pool IPAM. And it was crash-looping clusters from 1.17 to 1.20.


```
level=fatal msg="unable to run agent: failed to start: daemon configuration failed: failed to allocate router IPs: unable to allocate router IP for family ipv4: unable to allocate from pool \"hrz\" (family ipv4): pool not (yet) available" subsys=daemon
```

You don't normally see this, but it can happen. And when it does, it's an infra dev's nightmare.

The Cilium agent was restarting. Not once. Not twice. In an infinite loop.

And the only log message? A cryptic error that pointed nowhere useful.

This is how I fixed a deadlock in a 24k-GitHub star Kubernetes CNI, and how a simple retry with exponential backoff saved Cilium from crashing on startup.


## What are you on about?

For some context, Cilium is a security-focused Kubernetes CNI that provides networking, observability, and security for your clusters using eBPF. It does this by running agent pods on each node that handle IP allocation, network policy enforcement, and load balancing.

One of Cilium's IPAM (IP Address Management) modes is multi-pool IPAM. In this mode, the Cilium Operator centrally manages a pool of CIDR blocks and allocates per-node CIDRs to each agent as nodes join the cluster.

The agent then allocates individual IPs from its assigned CIDR to pods running on that node.

## The fatal flaw (haha, Fatal)

The problem surfaces when pre-allocation is set to 0 for a pool.

Here's what that means: when a new node joins the cluster, the agent needs to allocate a router IP, a critical infrastructure IP that the node uses for internal networking. The agent requests this IP from the operator.

But if pre-allocation is set to 0, the operator doesn't proactively provision CIDR blocks. It waits for demand.

So, when the agent requests a router IP, and the operator hasn't provisioned any CIDRs yet... The local pool is nil.

The agent then calls `AllocateNextFamilyWithoutSyncUpstream`, which returns `ErrPoolNotReadyYet`.

As a result, the agent would crash. Kubernetes would restart it. It would crash again. Restart. Crash. Restart. Yadiyadayada. No bueno.

## I wonder how, I wonder why

I started by tracing the IPAM allocation path. The key insight was understanding the difference between two allocation methods:

`AllocateNextFamilyWithoutSyncUpstream` -- fast path, doesn't sync with the operator

`AllocateNextFamily` -- triggers an upstream sync, telling the operator about pending demand

The agent was using the fast path. When the pool wasn't ready, it got `ErrPoolNotReadyYet` and panicked. But if it had used the sync path, it would have triggered the operator to provision a CIDR, and the allocation would succeed.

At this point, the fix seemed obvious: don't treat this error as fatal. Retry.

## I can fix him

I added a retry mechanism in `reallocateRouterIPs` that catches `ErrPoolNotReadyYet`, triggers an upstream sync via `TriggerUpstreamSync`, and waits for the pool to become available using exponential backoff.

The core of the solution is a shared helper function called `allocateNextFromPool` which would:

1. Attempt a fast-path allocation via `AllocateNextFamilyWithoutSyncUpstream`

2. On `ErrPoolNotReadyYet`, falls back to `AllocateNextFamily` (which triggers an upstream K8s sync) in an exponential backoff loop

```
func (r *infraIPAllocator) allocateNextFromPool(ctx context.Context, family ipam.Family, owner string) (*ipam.AllocationResult, error) {
    result, err := r.ipAllocator.AllocateNextFamilyWithoutSyncUpstream(family, owner, ipam.PoolDefault())
    if err == nil {
        return result, nil
    }

    var poolErr *ipam.ErrPoolNotReadyYet
    if !errors.As(err, &poolErr) {
        return nil, err
    }

    // The pool is not yet provisioned by the operator. Fall back to
    // AllocateNextFamily which triggers an upstream K8s sync to request
    // pool provisioning, then retry until the pool becomes available.
    bo := wait.Backoff{
        Duration: 500 * time.Millisecond,
        Factor:   1.5,
        Jitter:   0.1,
        // ... (backoff continues)
    }
    // ... retry loop with backoff
}
```


This helper replaced the direct calls in three places:

- `reallocateRouterIPs`

- `allocateHealthIPs`

- `allocateIngressIPs`

I also added the `AllocateNextFamily` method to the `ipamAllocator` interface to enable the upstream sync path:

```
type ipamAllocator interface {
    AllocateIPWithoutSyncUpstream(ip netip.Addr, owner string, pool ipam.Pool) (*ipam.AllocationResult, error)
    AllocateNextFamilyWithoutSyncUpstream(family ipam.Family, owner string, pool ipam.Pool) (result *ipam.AllocationResult, err error)
    AllocateNextFamily(family ipam.Family, owner string, pool ipam.Pool) (result *ipam.AllocationResult, err error) // NEW
    ExcludeIP(ip netip.Addr, owner string, pool ipam.Pool)
    ReleaseIP(ip netip.Addr, pool ipam.Pool) error
}
```

The exponential backoff prevents thundering herd problems while still allowing the agent to recover once the operator provisions the CIDR.

And of course, I also added unit tests covering:

- The retry success path

- Immediate non-pool errors

- Non-pool errors mid-backoff

End-to-end router IP reallocation with pool-not-ready retries.



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
