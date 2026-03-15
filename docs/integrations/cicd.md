# CI/CD Integration

FaultRay integrates into your CI/CD pipeline to gate deployments on infrastructure resilience.

## GitHub Actions

```yaml
name: Resilience Check

on:
  pull_request:
    paths:
      - 'terraform/**'
      - 'k8s/**'

jobs:
  faultray:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install FaultRay
        run: pip install faultray

      - name: Import infrastructure model
        run: faultray tf-import --dir ./terraform --output model.json

      - name: Run simulation
        run: faultray simulate -m model.json --json > results.json

      - name: Check threshold
        run: faultray evaluate -m model.json --threshold 70

      - name: Generate report
        if: always()
        run: faultray report -m model.json -o report.html

      - name: Upload report
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: resilience-report
          path: report.html
```

## GitLab CI

```yaml
resilience-check:
  image: python:3.12
  stage: test
  script:
    - pip install faultray
    - faultray tf-import --dir ./terraform --output model.json
    - faultray simulate -m model.json --json > results.json
    - faultray evaluate -m model.json --threshold 70
  artifacts:
    paths:
      - results.json
    when: always
```

## Jenkins

```groovy
pipeline {
    agent any
    stages {
        stage('Resilience Check') {
            steps {
                sh 'pip install faultray'
                sh 'faultray tf-import --dir ./terraform --output model.json'
                sh 'faultray simulate -m model.json --json > results.json'
                sh 'faultray evaluate -m model.json --threshold 70'
            }
            post {
                always {
                    archiveArtifacts artifacts: 'results.json'
                }
            }
        }
    }
}
```

## Exit Codes for CI/CD

FaultRay uses exit codes to signal pipeline outcomes:

| Exit Code | Meaning | CI/CD Action |
|-----------|---------|--------------|
| 0 | All checks passed | Continue pipeline |
| 2 | Critical issues found | Block deployment |
| 3 | Score below threshold | Block deployment |

## Best Practices

1. **Set a minimum threshold** — Use `--threshold 70` to enforce a minimum resilience score.
2. **Run on infrastructure changes** — Trigger only when Terraform, Kubernetes, or IaC files change.
3. **Archive reports** — Always save HTML reports as artifacts for post-merge review.
4. **Compare before/after** — Use `faultray diff` to catch resilience regressions in PRs.
