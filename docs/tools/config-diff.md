# Config Diff Tool

## Overview
The Config Diff tool allows you to compare infrastructure configurations between different environments or git revisions. It helps identifying drift or intended changes before applying them.

## Usage

```bash
infra diff --env prod --compare-with dev
```

## Features
- Compare resource definitions between environments.
- Detect added, modified, and removed resources.
- Support for filtering by provider or resource type.
