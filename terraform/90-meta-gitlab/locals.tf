
# GitLab HTTP backend credentials (read at plan time from gitignored file)
locals {
  _gl_creds   = jsondecode(file("${path.root}/../backend-state.json"))
  _state_base = "https://gitlab.com/api/v4/projects/83830958/terraform/state"
  _state_auth = {
    username = local._gl_creds.username
    password = local._gl_creds.token
  }

  project_labels = {
    # Alerts and Critical Issues (Red/Crimson)
    "bug"      = { color = "#e03131", description = "Outlines a bug or defect in the system" }
    "security" = { color = "#c92a2a", description = "Security vulnerabilities or improvements" }

    # Engineering and Features (Purple/Violet/Indigo)
    "feature"     = { color = "#8e44ad", description = "New functional features to be implemented" }
    "enhancement" = { color = "#7048e8", description = "New feature requests or system enhancements" }
    "CI"          = { color = "#4c6ef5", description = "Continuous Integration related configurations or MRs" }

    # Fixes and Code Improvements (Green/Teal)
    "fix"           = { color = "#2ecc71", description = "Fixes to existing bugs or features" }
    "refactor"      = { color = "#12b886", description = "Code refactoring without behavioral changes" }
    "documentation" = { color = "#15aabf", description = "Improvements or additions to documentation" }
    "observability" = { color = "#fd7e14", description = "Metrics, logs, tracing and monitoring tasks" }

    # Collaboration and Community (Mint/Pink)
    "good first issue" = { color = "#099268", description = "Easy issue suitable for new contributors" }
    "help wanted"      = { color = "#40c057", description = "Extra help is needed to resolve this issue" }
    "question"         = { color = "#e64980", description = "General questions or inquiries" }

    # Workflow and Status (Yellow)
    "pending" = { color = "#fab005", description = "Awaiting further actions or review" }

    # Disposition and Muted (Grays)
    "duplicate" = { color = "#868e96", description = "Similar or duplicate issues/MRs" }
    "wontfix"   = { color = "#adb5bd", description = "Decided not to fix or implement" }
    "invalid"   = { color = "#495057", description = "Issues or MRs that are no longer valid" }
  }
}
