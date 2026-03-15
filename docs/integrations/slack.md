# Slack Integration

FaultRay can send simulation results and alerts to Slack channels via webhooks or the Slack Bot integration.

## Webhook Setup

### 1. Create a Slack Incoming Webhook

1. Go to your Slack workspace settings
2. Navigate to **Apps > Incoming Webhooks**
3. Create a new webhook and select a channel
4. Copy the webhook URL

### 2. Configure FaultRay

```bash
export FAULTRAY_SLACK_WEBHOOK="https://hooks.slack.com/services/T.../B.../..."
```

Or in your configuration file:

```yaml
notifications:
  slack:
    webhook_url: "https://hooks.slack.com/services/T.../B.../..."
    channel: "#infrastructure"
    notify_on:
      - critical
      - score_change
```

### 3. Send results to Slack

```bash
faultray simulate -m model.json --notify slack
```

## Notification Types

| Event | Description | Default |
|-------|-------------|---------|
| `critical` | Critical vulnerability detected | Enabled |
| `score_change` | Score changed by more than 5 points | Enabled |
| `simulation_complete` | Simulation finished | Disabled |
| `threshold_breach` | Score dropped below threshold | Enabled |

## Message Format

FaultRay sends rich Slack messages with:

- Resilience score with color-coded status
- Number of critical/warning findings
- Top 3 most impactful issues
- Link to the full HTML report (if hosted)

## Slack Bot (Advanced)

For interactive features, install the FaultRay Slack Bot:

```bash
faultray slack-bot install --token xoxb-YOUR-BOT-TOKEN
```

Bot commands:

| Command | Description |
|---------|-------------|
| `/faultray scan` | Trigger an infrastructure scan |
| `/faultray score` | Show current resilience score |
| `/faultray report` | Generate and share a report |
