# Conversion Engine Project Info

## Purpose

This project is based on two source documents:

1. `TRP1 Challenge Week 10_ Conversion Engine for Sales Automation.pdf`
2. `Supporting Scenario of The Conversion Engine.pdf`

This file is an implementation-free project brief. It captures the business context, workflow, data sources, constraints, and expected outputs described in those PDFs so the project can be planned from a solid reference.

## Recommended Framing

Use the **Tenacious Consulting and Outsourcing** challenge as the primary project definition, and use the **Acme ComplianceOS** scenario as a supporting reference model.

Why:

- The Tenacious document is the direct challenge brief for an automated lead generation and conversion system.
- The Acme document provides a more detailed example of how a production-grade conversion workflow can be structured, especially around qualification, CRM logging, calendar booking, evaluation, and operational guardrails.

## Core Business Problem

The project is about building a conversion engine that can:

- identify prospects from public data
- qualify those prospects using real signals
- run a nurture sequence
- move qualified prospects toward a booked discovery call
- record the process in a CRM-friendly way

In the Tenacious version, the target company is a real B2B consulting and outsourcing firm serving technology-driven companies. The system is meant to help the executive team evaluate whether automated outbound and qualification can support deployment.

In the supporting Acme scenario, the same general pattern is applied to a B2B SaaS compliance company, with stronger detail around SMS, CRM, enrichment, and measurement.

## Primary Project Scenario

### Main client

Tenacious Consulting and Outsourcing

### Main outcome

Create a system that:

- finds prospective clients from public sources
- qualifies them against intent and business signals
- sends outreach and nurture communication
- books discovery calls with a Tenacious delivery lead

### Channel strategy

- Email is the primary outreach channel for Tenacious prospects.
- SMS is a secondary channel, mainly for warm-lead scheduling or handoff.

## Supporting Scenario Insights

The Acme ComplianceOS document adds useful structure for how the project should be thought about operationally:

- the first 72 hours of lead handling matter most
- response speed is a major business issue
- qualification errors reduce conversion
- every interaction should be logged as a structured record
- booking should connect directly to a real calendar workflow
- the system should be evaluated with clear traces, latency, and failure analysis

## End-to-End Workflow

Across both PDFs, the intended workflow looks like this:

1. Discover or receive a lead.
2. Match the lead to public firmographic data.
3. Enrich the lead with relevant intent or business signals.
4. Generate an internal brief that explains why the lead is promising.
5. Send outreach or continue the nurture sequence.
6. Handle replies while maintaining conversation state.
7. Qualify the lead.
8. Offer and book a discovery call.
9. write the interaction history and enrichment results into CRM records.
10. Measure latency, quality, failures, and business value.

## Important Data Sources

### From the Tenacious brief

- Crunchbase ODM sample
  - primary firmographic source
- layoffs.fyi
  - hiring or contraction signal
- public job posts
  - velocity and hiring signal
- public leadership-change signals
  - executive or technical leadership changes
- tau2-bench
  - evaluation benchmark for conversational agent behavior

### From the supporting scenario

- Crunchbase ODM sample
  - company identity and firmographics
- CFPB complaint data
  - example of an external domain-specific risk/enrichment source
- tau2-bench
  - benchmark and adversarial evaluation layer
- production traces
  - logs, latencies, tool usage, and conversation histories

## Required Information Objects

Based on the PDFs, the project revolves around internal structured outputs such as:

- lead or prospect record
- enrichment brief
- hiring signal brief
- competitor gap brief
- qualification status
- conversation transcript
- CRM activity log
- booking record
- trace log

These are useful planning objects even if no implementation is done yet.

## Qualification Logic

The documents suggest that leads should not be qualified only from one signal. Qualification should combine:

- company firmographics
- recent funding or growth signals
- job-post activity
- layoffs or contraction signals
- leadership changes
- sector context
- confidence in the evidence

The Acme scenario reinforces an important rule: the system should not over-claim what the data proves. Weak signals should remain weak signals.

## CRM and Booking Expectations

Even though this project is not being implemented yet, the intended design clearly assumes:

- CRM records are updated for every meaningful interaction
- enrichment timestamps are stored
- qualification state is visible
- meeting booking is part of the core conversion flow
- conversation history should be auditable

The PDFs repeatedly position HubSpot-style records and calendar booking as central parts of the conversion engine, not optional extras.

## Constraints and Guardrails

### Data handling

- No real customer data should be used unless explicitly provided and allowed.
- In the Tenacious challenge, challenge-week prospects are synthetic profiles derived from public firmographics plus fictional contact details.
- Public-source grounding is important. The system should rely on reproducible sources rather than invented facts.

### Outreach behavior

- Outreach should be grounded in public evidence.
- Messages should avoid exaggerated claims.
- Channel handoff should be intentional, not random.

### Evaluation mindset

Both PDFs treat evaluation as part of the product definition, not an afterthought. The project should be designed to answer:

- Did the engine identify the right leads?
- Did it qualify them correctly?
- Did it convert them into meetings?
- Was it fast enough?
- Were the claims evidence-based?
- What failure modes matter most?

## Success Criteria

At a high level, the project is successful if it can demonstrate:

- credible lead discovery from public data
- useful enrichment and qualification
- convincing nurture or scheduling flow
- movement from outreach to booked call
- accurate CRM-ready records
- measurable speed and quality
- clear failure analysis and business reasoning

## How The Two PDFs Fit Together

The cleanest way to combine them is:

- **Primary business case:** Tenacious lead generation and conversion for consulting and outsourcing sales
- **Operational pattern:** Acme's production-grade CRM, SMS, booking, and evaluation structure
- **Shared backbone:** public data enrichment, qualification, nurture, CRM logging, and measurable conversion outcomes

## Recommended Project Scope For Now

Since you asked for information only and no implementation, your project can currently be defined as:

> A sales conversion engine for Tenacious Consulting and Outsourcing that uses public company signals to identify and qualify prospects, supports outreach and nurture across email with optional SMS handoff, and is designed to move qualified prospects into booked discovery calls while maintaining auditable CRM-ready records.

## Suggested Next Non-Code Artifacts

If you want to keep building the project definition without coding yet, the next useful documents would be:

- `problem-statement.md`
- `project-scope.md`
- `system-workflow.md`
- `data-sources.md`
- `success-metrics.md`
- `risks-and-guardrails.md`

## Assumption

This brief assumes you want the project anchored to the Tenacious challenge and informed by the Acme scenario, rather than replacing the Tenacious scenario entirely with the Acme one.
