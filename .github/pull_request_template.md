## CI/CD Policy Checklist

- [ ] This PR does **not** introduce direct Kubernetes deploy logic in this service repo (no `kubectl`, no `kustomize`, no `runs-on: [self-hosted, ...]`).
- [ ] Deployment changes (image/config) are handled via `faultmaven-enterprise-infra` promotion + overlays.


