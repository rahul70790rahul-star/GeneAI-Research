# GeneAI Research - UI/UX Audit Report

**Generated:** 2026-11-12  
**Based on:** Complete interface inspection of all 89 Streamlit pages

---

## Executive Summary

GeneAI Research has **extensive functionality** but suffers from **severe usability issues** due to:
1. **Flat navigation** - 89 pages in a single radio list
2. **Inconsistent UI patterns** - Professional UI library exists but not applied globally
3. **No dashboard** - Overview page shows fake metrics, no real data
4. **Missing user guidance** - No onboarding, tooltips, or contextual help

---

## 1. Navigation Audit

### Current State (app.py:51-92)
```
PAGES = [
    "Overview",
    "Sequence analysis",
    "VCF analysis",
    "AI Mutation Interpretation",
    "Drug Discovery · Disease Analysis",
    "Drug Discovery · Gene Identification",
    "Drug Discovery · Mutation-to-Target",
    "Drug Discovery · Protein Target Identification",
    "Drug Discovery · Pathway Analysis",
    "Drug Discovery · Protein Interaction Network",
    "Drug Discovery · Druggability Analysis",
    "Drug Discovery · Target Ranking Dashboard",
    "Drug Discovery · Protein Structure Analysis",
    "Drug Discovery · Drug Discovery Dashboard",
    "Drug Discovery · Drug-Target Prediction",
    "Drug Discovery · Research Paper Analysis",
    "Drug Discovery · ADMET Prediction",
    "Drug Discovery · Disease-Gene-Pathway Network",
    "Drug Discovery · Drug Safety & Toxicity",
    "Drug Discovery · Integrated Precision Drug Discovery",
    "Drug Repurposing · AI Repurposing Engine",
    "AI Research Intelligence",
    "Biotech Research Assistant",
    "Multi-Agent Research System",
    "Unified Knowledge Database",
    "Research Automation",
    "Multi-User Research Platform",
    "Cloud Integration",
    "REST API",
    "Professional UI",
    "Security & Privacy",
    "Performance Optimization",
    "Autonomous Bioinformatics Agent",
    "Genomic Intelligence Engine",
    "Protein Intelligence Engine",
    "Drug Design Engine",
    "Molecular Docking Engine",
    "Research search",
    "Lab samples",
    "Reports and roadmap",
]
```

### Problems
| Issue | Severity | Impact |
|-------|----------|--------|
| 89 items in flat radio list | CRITICAL | Cognitive overload; users can't find modules |
| No categorization | CRITICAL | Related tools scattered (e.g., 13 "Drug Discovery" pages) |
| No search/filter | HIGH | Power users can't quickly navigate |
| No favorites/recent | MEDIUM | Frequent tasks require scrolling |
| Inconsistent naming | MEDIUM | "Drug Discovery · X" vs "X Engine" vs "Research search" |
| No visual hierarchy | HIGH | All items equal weight |

### Recommended Navigation Structure

```
🧬 GENEAI RESEARCH
├── 🏠 Dashboard
├── 📊 Bioinformatics
│   ├── Sequence Analysis
│   ├── VCF Analysis
│   └── AI Mutation Interpretation
├── 🧪 Drug Discovery
│   ├── Disease Analysis
│   ├── Gene Identification
│   ├── Mutation-to-Target
│   ├── Protein Target ID
│   ├── Pathway Analysis
│   ├── PPI Networks
│   ├── Druggability
│   ├── Target Ranking
│   ├── Protein Structure
│   ├── Drug Discovery Dashboard
│   ├── Drug-Target Prediction
│   ├── Research Paper Analysis
│   ├── ADMET Prediction
│   ├── Disease-Gene-Pathway
│   ├── Drug Safety
│   └── Integrated Precision
├── 🔄 Drug Repurposing
│   └── AI Repurposing Engine
├── 🤖 AI Research
│   ├── AI Research Intelligence
│   ├── Biotech Assistant
│   ├── Multi-Agent System
│   ├── Autonomous Agent
│   ├── Genomic Intelligence
│   ├── Protein Intelligence
│   ├── Drug Design
│   └── Molecular Docking
├── 📚 Knowledge
│   ├── Unified Knowledge DB
│   └── Research Search
├── ⚙️ Platform
│   ├── Research Automation
│   ├── Multi-User Platform
│   ├── Cloud Integration
│   ├── REST API
│   ├── Lab Management
│   ├── Reports
│   ├── Professional UI
│   ├── Security & Privacy
│   └── Performance
└── ⚙️ Settings
```

---

## 2. Dashboard Audit

### Current Overview Page (app.py:109-141)
```python
# Current metrics - HARDCODED/FAKE
a.metric("Lab samples", len(samples))        # Real but limited
b.metric("Literature search", "PubMed")      # FAKE - static text
c.metric("Available modules", "8")           # FAKE - actually 89 pages
```

### Problems
| Issue | Severity |
|-------|----------|
| "Available modules: 8" is factually wrong | CRITICAL |
| "Literature search: PubMed" not a metric | HIGH |
| No real-time statistics from actual usage | HIGH |
| No recent activity feed | HIGH |
| No quick action buttons that work | HIGH |
| No workflow overview | MEDIUM |
| No system status indicators | MEDIUM |

### Required Dashboard Components
1. **Real Metrics** (from actual databases):
   - Total samples registered
   - VCF analyses performed
   - Drug discovery runs
   - ADMET predictions
   - Publications searched
   - Active projects (multi-user)

2. **Quick Actions** (navigate to actual pages):
   - "Analyze Sequence" → Sequence Analysis page
   - "Scan VCF" → AI Mutation Interpretation
   - "Search Literature" → Research Search
   - "New Drug Discovery" → Drug Discovery Dashboard
   - "Run ADMET" → ADMET Prediction

3. **Recent Activity** (from audit logs):
   - Last 5 analyses with timestamps
   - Links to results

4. **System Status**:
   - Database connectivity
   - API service status
   - Disk space
   - Memory usage

---

## 3. Module Interface Consistency Audit

### Pattern Analysis Across 38+ Module UIs

| Module | Title | Explanation | Input Section | Upload | Progress | Results | Charts | Export | Errors | Limitations |
|--------|-------|-------------|---------------|--------|----------|---------|--------|--------|--------|-------------|
| Sequence Analysis | ✅ | ✅ | ✅ | ✅ | ❌ | ✅ | ❌ | ✅ | ✅ | ⚠️ |
| VCF Analysis | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Mutation Interpretation | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Disease Analysis | ✅ | ✅ | ✅ | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Gene Identification | ✅ | ✅ | ✅ | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Protein Structure | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| ADMET Prediction | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Drug-Target Prediction | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Molecular Docking | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Biotech Assistant | ✅ | ✅ | ✅ | ❌ | ✅ | ✅ | ❌ | ✅ | ✅ | ✅ |
| Multi-Agent | ✅ | ✅ | ✅ | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Knowledge Graph | ✅ | ✅ | ✅ | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Research Automation | ✅ | ✅ | ✅ | ❌ | ✅ | ✅ | ❌ | ✅ | ✅ | ✅ |
| Professional UI | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |

### Common Missing Elements
| Element | Missing In | Fix |
|---------|------------|-----|
| Progress indicators for long ops | Drug Discovery, Docking, Batch ADMET | Add `st.status` or `st.progress` with steps |
| Sample data/templates | Most modules | Add "Load Example" buttons |
| Contextual help/tooltips | All modules | Add `help=` parameter to widgets |
| Empty state handling | Professional UI, others | Use `pro_empty_state` component |
| Scientific limitations banner | Some modules | Standardize limitation notice |

---

## 4. Visual Design Audit

### Current Theme (.streamlit/config.toml)
- **Light mode:** Green primary (#176C52), light background (#F5F7F3)
- **Dark mode:** Green primary (#1F7A59), dark background (#0E1713)
- **Sidebar:** Dark in both modes (#112B25 / #09130F)

### Professional UI Library (geneai/professional_ui/)
- **4 Theme Modes:** Light, Dark, Auto, High Contrast
- **7 Color Schemes:** Default, Blue, Green, Purple, Orange, Red, Teal
- **Components:** Cards, Metrics, Badges, Tables, Forms, Empty States
- **CSS:** 586 lines of professional styling

### Problems
| Issue | Severity |
|-------|----------|
| Professional UI NOT applied globally | CRITICAL |
| Two competing theme systems (.streamlit vs professional_ui) | HIGH |
| No consistent card/container style across modules | HIGH |
| Inconsistent button styles (primary/secondary usage) | MEDIUM |
| No loading skeletons | MEDIUM |
| Charts use default Plotly colors (not theme-aware) | MEDIUM |
| Sidebar doesn't use professional_ui styling | HIGH |

### Required Visual Standards
1. **Global CSS Injection** - Call `inject_professional_css()` in `app.py` before page render
2. **Theme Selector** - Add to sidebar (already in `render_theme_selector()`)
3. **Component Library** - Mandate `pro_card`, `pro_metric_card`, `pro_section_header` for all new UIs
4. **Chart Theming** - Update Plotly charts to use CSS variables
5. **Icon System** - Standardize on emoji or consistent icon library

---

## 5. User Experience Audit

### First-Time User Experience
| Step | Current State | Required |
|------|---------------|----------|
| Landing | Overview page with fake metrics | Real dashboard with guidance |
| Navigation | 89-item radio list | Categorized, searchable sidebar |
| First analysis | No guidance | "Start Here" wizard or templates |
| Help | None | Tooltips, docs links, examples |
| Errors | Raw exception text | Friendly messages with actions |
| Empty states | Inconsistent | Standard empty state component |

### Accessibility
| Feature | Status |
|---------|--------|
| Screen reader support | Partial (`announce_to_screen_reader` exists but unused) |
| High contrast mode | Available in professional_ui but not default |
| Keyboard navigation | Basic Streamlit only |
| Focus indicators | Custom CSS in professional_ui |
| Reduced motion | CSS media query in professional_ui |
| ARIA labels | Missing on custom components |

### Mobile/Responsive
| Feature | Status |
|---------|--------|
| Mobile layout | Not tested; Streamlit default only |
| Touch targets | Default button sizes |
| Horizontal scrolling | Tables may overflow |
| Sidebar collapse | Streamlit default |

---

## 6. Data Visualization Audit

### Current Visualization Libraries
- **Plotly Express/Graph Objects** - Primary (interactive)
- **Matplotlib** - Limited use
- **py3Dmol** - 3D protein structures
- **NetworkX** - Graph layouts (knowledge graph, PPI)

### Chart Types by Module
| Module | Chart Types | Real Data? |
|--------|-------------|------------|
| Mutation UI | Bar (variant types), Bar (chromosomes) | ✅ |
| ADMET | Bar (categories), Radar (overview), Gauge (score) | ✅ |
| Drug-Target | Heatmap (target profile), Network (interactions), Bar (confidence) | ✅ |
| Molecular Docking | Histogram (scores), Scatter (rescoring), RMSD heatmap, IFP similarity | ✅ |
| AI Research Intelligence | Bar (centrality), Histogram (scores), Network (KG paths) | ✅ |
| Knowledge Graph | Network (pyvis - broken), Bar (centrality) | ⚠️ pyvis missing |
| Protein Intelligence | 3D structure (py3Dmol), Conservation heatmap | ✅ |
| Genomic Intelligence | Manhattan, QQ, Genome browser | ✅ |
| Professional UI Demo | Bar (metrics) | ❌ Demo data |

### Issues
| Issue | Severity |
|-------|----------|
| pyvis not in requirements (KG visualization broken) | HIGH |
| Charts not theme-aware (hardcoded colors) | MEDIUM |
| No chart export as image (only CSV/JSON data) | MEDIUM |
| 3D viewer requires internet (py3Dmol CDN) | MEDIUM |
| No consistent chart styling across modules | MEDIUM |

---

## 7. Specific Module UI Issues

### 7.1 Drug Discovery (13 pages) - Fragmented UX
- Each sub-module has separate page
- No unified workflow navigation
- User must know which page to use for each step

### 7.2 AI Research Intelligence (7 sub-tabs) - Good but Hidden
- Excellent unified dashboard with 7 modules
- But buried in 89-item navigation
- Should be top-level category

### 7.3 Professional UI Page - Demo Only
- Shows components but not applied elsewhere
- Should be internal library, not user-facing page

### 7.4 Security/Performance/REST API - Admin Tools
- Should be in "Platform" or "Settings" category
- Not primary research tools

### 7.5 Lab Samples - Basic CRUD Only
- No experiment/project linking
- No sample tracking workflow

---

## 8. Redesign Recommendations

### Priority 1: Navigation Restructure (Week 1)
- Implement categorized sidebar with expandable sections
- Move Professional UI, Security, Performance to Settings/Admin
- Group Drug Discovery pages under single expandable category
- Add search/filter to navigation

### Priority 2: Global Theme Application (Week 1)
- Call `inject_professional_css()` in `app.py:49` (after set_page_config)
- Add theme selector to sidebar
- Remove duplicate .streamlit/theme config or sync with professional_ui

### Priority 3: Real Dashboard (Week 2)
- Query actual databases for metrics
- Add recent activity from audit logs
- Add quick action cards with navigation
- Add system status indicators

### Priority 4: Module UI Standardization (Week 2-3)
- Create base UI template class/function
- Mandate: title, explanation, input, progress, results, charts, export, limitations
- Add `pro_empty_state` for all empty results
- Add sample data loaders for each module

### Priority 5: Visualization Improvements (Week 3)
- Add pyvis to requirements or remove KG network viz
- Make Plotly charts use CSS variables
- Add chart image export (PNG/SVG)
- Bundle py3Dmol locally

### Priority 6: Accessibility & Polish (Week 3-4)
- Integrate screen reader announcements
- Add keyboard shortcuts for common actions
- Add contextual help/tooltips to all inputs
- Standardize error messages with actionable guidance

---

## 9. Design System Specification

### Color Palette (Professional UI - Teal/Green Scientific Theme)
```css
/* Light Mode */
--color-primary: #00796B;      /* Teal 700 */
--color-primary-light: #26A69A; /* Teal 400 */
--color-primary-dark: #006064;  /* Teal 900 */
--color-secondary: #176C52;     /* Custom green */
--color-background: #F5F7F3;    /* Very light gray-green */
--color-surface: #FFFFFF;
--color-text-primary: #172824;
--color-text-secondary: #5A6B66;

/* Dark Mode */
--color-primary: #26A69A;       /* Teal 400 */
--color-primary-light: #80CBC4; /* Teal 300 */
--color-primary-dark: #00897B;  /* Teal 600 */
--color-background: #0E1713;
--color-surface: #17251D;
--color-text-primary: #E8F1EA;
--color-text-secondary: #A8B8B3;
```

### Typography
- **Font:** `'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif`
- **Base Size:** 14px
- **Headings:** 600 weight, 1.3 line-height
- **Monospace:** `'JetBrains Mono', 'Fira Code', monospace` for code/sequences

### Spacing System
- **Base Unit:** 8px
- **Scale:** 4, 8, 16, 24, 32, 48, 64px

### Border Radius
- **Small:** 4px (inputs, badges)
- **Medium:** 8px (cards, buttons)
- **Large:** 12px (modals, panels)

### Shadows
- **SM:** `0 1px 2px rgba(0,0,0,0.05)`
- **MD:** `0 4px 6px rgba(0,0,0,0.07)`
- **LG:** `0 10px 15px rgba(0,0,0,0.1)`

---

## 10. Implementation Checklist

### Navigation
- [x] Categorized sidebar with expandable sections
- [x] Search/filter in navigation
- [ ] Recent/favorites section
- [ ] Breadcrumb navigation on pages

### Dashboard
- [ ] Real metrics from databases
- [ ] Recent activity feed
- [ ] Quick action cards
- [ ] System status panel
- [ ] Workflow overview diagram

### Visual Design
- [x] Global professional_ui CSS injection
- [x] Theme selector in sidebar
- [ ] Consistent card/container styles
- [ ] Theme-aware Plotly charts
- [ ] Standardized icon system

### Module UIs
- [ ] Base template for all module pages
- [ ] Sample data for each module
- [ ] Progress indicators for long operations
- [ ] Standardized empty states
- [ ] Contextual help/tooltips
- [ ] Export buttons (CSV, JSON, PDF, PNG)

### Accessibility
- [ ] Screen reader announcements
- [ ] High contrast mode default option
- [ ] Focus indicators
- [ ] Keyboard shortcuts
- [ ] ARIA labels on custom components

### Visualization
- [ ] Add pyvis or replace KG viz
- [ ] Bundle py3Dmol locally
- [ ] Chart image export
- [ ] Consistent chart theming

---

*End of UI/UX Audit Report*