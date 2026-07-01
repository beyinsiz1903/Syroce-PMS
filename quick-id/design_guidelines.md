{
  "design_personality": {
    "brand_attributes": [
      "güvenilir (kişisel veriler)",
      "operatör-odaklı (hızlı işlem)",
      "kurumsal / PMS hissi",
      "tablet + masaüstü ergonomisi",
      "hata-toleranslı (yeniden dene, geri al, düzenle)"
    ],
    "visual_style": "Swiss-leaning enterprise (grid + typography) + soft hospitality warmth (mint/teal accents). Light background mandatory, no translucent app surfaces.",
    "layout_principles": [
      "Left navigation + top action bar pattern for PMS speed",
      "Scanning pages use split layout: camera on left, extracted form on right (desktop); stacked (tablet/phone)",
      "Tables are primary surface: strong row height, sticky header, dense-but-readable",
      "Only a small decorative gradient band in hero/header areas (<=20% viewport)"
    ]
  },

  "design_tokens": {
    "css_custom_properties": {
      "notes": "Update /app/frontend/src/index.css :root HSL tokens to match below. Keep background white/light; avoid dark gradients. Define additional hotel brand tokens as CSS vars (non-shadcn) for charts/status chips.",
      "base": {
        "--background": "0 0% 100%",
        "--foreground": "222 47% 11%",
        "--card": "0 0% 100%",
        "--card-foreground": "222 47% 11%",
        "--popover": "0 0% 100%",
        "--popover-foreground": "222 47% 11%",

        "--primary": "201 79% 29%",
        "--primary-foreground": "210 40% 98%",

        "--secondary": "204 20% 96%",
        "--secondary-foreground": "222 47% 11%",

        "--muted": "204 20% 96%",
        "--muted-foreground": "215 16% 40%",

        "--accent": "166 45% 92%",
        "--accent-foreground": "201 79% 20%",

        "--border": "214 18% 88%",
        "--input": "214 18% 88%",
        "--ring": "201 79% 29%",

        "--destructive": "0 72% 52%",
        "--destructive-foreground": "210 40% 98%",

        "--radius": "0.75rem"
      },
      "extended_brand_vars": {
        "--brand-ink": "#0B1220",
        "--brand-slate": "#334155",
        "--brand-teal": "#0F766E",
        "--brand-teal-soft": "#E6F7F3",
        "--brand-sky": "#0B5E8A",
        "--brand-sky-soft": "#E8F3FA",
        "--brand-amber": "#B45309",
        "--brand-amber-soft": "#FFF7ED",
        "--brand-success": "#0F766E",
        "--brand-success-soft": "#ECFDF5",
        "--brand-danger": "#B42318",
        "--brand-danger-soft": "#FEF3F2",
        "--brand-warning": "#B45309",
        "--brand-warning-soft": "#FFFBEB",
        "--brand-info": "#075985",
        "--brand-info-soft": "#EFF6FF"
      },
      "shadows": {
        "--shadow-sm": "0 1px 2px rgba(15, 23, 42, 0.06)",
        "--shadow-md": "0 10px 18px rgba(15, 23, 42, 0.08)",
        "--shadow-focus": "0 0 0 4px rgba(11, 94, 138, 0.18)"
      },
      "spacing": {
        "--space-1": "4px",
        "--space-2": "8px",
        "--space-3": "12px",
        "--space-4": "16px",
        "--space-6": "24px",
        "--space-8": "32px"
      }
    },

    "color_palette": {
      "primary": {
        "name": "Bosporus Blue",
        "hex": "#0B5E8A",
        "usage": "Primary buttons, links, focus ring, key CTAs (Kaydet, Tara)"
      },
      "accent": {
        "name": "Mint Check-in",
        "hex": "#0F766E",
        "usage": "Success states, check-in status, positive chips"
      },
      "neutral": {
        "bg": "#FFFFFF",
        "surface": "#F7FAFC",
        "border": "#E2E8F0",
        "text": "#0B1220",
        "muted_text": "#475569"
      },
      "state_colors": {
        "success": "#0F766E",
        "warning": "#B45309",
        "danger": "#B42318",
        "info": "#075985"
      },
      "allowed_gradients": [
        {
          "name": "Header wash (allowed: subtle, <=20% viewport)",
          "css": "linear-gradient(135deg, rgba(11,94,138,0.10), rgba(15,118,110,0.08), rgba(255,255,255,0))",
          "usage": "Top header background band on Dashboard/Scan pages only"
        }
      ],
      "texture": {
        "noise_overlay": "Use a very subtle CSS noise (opacity 0.04-0.06) on page background only; avoid on cards/text areas.",
        "css_snippet": ".noise::before{content:'';position:absolute;inset:0;background-image:url('data:image/svg+xml;utf8,<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"120\" height=\"120\"><filter id=\"n\"><feTurbulence type=\"fractalNoise\" baseFrequency=\"0.9\" numOctaves=\"2\" stitchTiles=\"stitch\"/></filter><rect width=\"120\" height=\"120\" filter=\"url(%23n)\" opacity=\"0.45\"/></svg>');opacity:.05;pointer-events:none;border-radius:inherit;}"
      }
    },

    "typography": {
      "google_fonts": [
        {
          "family": "Space Grotesk",
          "weights": ["400", "500", "600", "700"],
          "usage": "Headings + KPI numbers"
        },
        {
          "family": "Inter",
          "weights": ["400", "500", "600"],
          "usage": "Body, tables, forms (Turkish diacritics friendly)"
        }
      ],
      "font_stack": {
        "heading": "'Space Grotesk', ui-sans-serif, system-ui",
        "body": "'Inter', ui-sans-serif, system-ui"
      },
      "type_scale_tailwind": {
        "h1": "text-4xl sm:text-5xl lg:text-6xl font-semibold tracking-tight",
        "h2": "text-base md:text-lg text-muted-foreground",
        "kpi": "text-2xl sm:text-3xl font-semibold tabular-nums",
        "body": "text-sm sm:text-base",
        "label": "text-xs font-medium text-muted-foreground",
        "table": "text-sm"
      }
    },

    "radii": {
      "app": "rounded-xl",
      "card": "rounded-xl",
      "button": "rounded-lg (8-12px range)",
      "chip": "rounded-full"
    }
  },

  "grid_and_responsiveness": {
    "container": {
      "desktop": "max-w-[1400px] mx-auto px-6",
      "tablet": "px-4",
      "mobile": "px-4"
    },
    "dashboard_grid": {
      "kpi_row": "grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4",
      "main_split": "grid grid-cols-1 lg:grid-cols-[1fr_420px] gap-4"
    },
    "scan_page_grid": {
      "desktop": "grid grid-cols-1 xl:grid-cols-[minmax(520px,1fr)_520px] gap-4",
      "tablet": "grid grid-cols-1 gap-3 (camera first, then form)",
      "camera_aspect": "aspect-[4/3] for tablet; aspect-video for desktop"
    },
    "table_density": {
      "row_height": "h-12 (default) with comfortable padding",
      "sticky": "sticky top-0 bg-background/95 backdrop-blur (ONLY header bar; cards stay solid white)",
      "horizontal_scroll": "overflow-x-auto for tablet"
    }
  },

  "components": {
    "component_path": {
      "shadcn_primary": [
        {"name": "Button", "path": "/app/frontend/src/components/ui/button.jsx"},
        {"name": "Input", "path": "/app/frontend/src/components/ui/input.jsx"},
        {"name": "Label", "path": "/app/frontend/src/components/ui/label.jsx"},
        {"name": "Textarea", "path": "/app/frontend/src/components/ui/textarea.jsx"},
        {"name": "Card", "path": "/app/frontend/src/components/ui/card.jsx"},
        {"name": "Badge", "path": "/app/frontend/src/components/ui/badge.jsx"},
        {"name": "Table", "path": "/app/frontend/src/components/ui/table.jsx"},
        {"name": "Tabs", "path": "/app/frontend/src/components/ui/tabs.jsx"},
        {"name": "Dialog", "path": "/app/frontend/src/components/ui/dialog.jsx"},
        {"name": "Drawer", "path": "/app/frontend/src/components/ui/drawer.jsx"},
        {"name": "Sheet", "path": "/app/frontend/src/components/ui/sheet.jsx"},
        {"name": "Select", "path": "/app/frontend/src/components/ui/select.jsx"},
        {"name": "Popover", "path": "/app/frontend/src/components/ui/popover.jsx"},
        {"name": "Calendar", "path": "/app/frontend/src/components/ui/calendar.jsx"},
        {"name": "Dropdown Menu", "path": "/app/frontend/src/components/ui/dropdown-menu.jsx"},
        {"name": "Pagination", "path": "/app/frontend/src/components/ui/pagination.jsx"},
        {"name": "Tooltip", "path": "/app/frontend/src/components/ui/tooltip.jsx"},
        {"name": "Sonner Toast", "path": "/app/frontend/src/components/ui/sonner.jsx"},
        {"name": "Skeleton", "path": "/app/frontend/src/components/ui/skeleton.jsx"},
        {"name": "Progress", "path": "/app/frontend/src/components/ui/progress.jsx"}
      ],
      "icons": {
        "library": "lucide-react",
        "examples": ["Camera", "ScanLine", "Users", "History", "LogIn", "LogOut", "Filter", "Search", "ShieldCheck", "RefreshCcw", "Edit3"]
      }
    },

    "buttons": {
      "variants": {
        "primary": {
          "usage": "Tara / Yakala / Kaydet / Check-in",
          "tailwind": "bg-[var(--brand-sky)] text-white hover:bg-[#094C6E] focus-visible:ring-4 focus-visible:ring-[rgba(11,94,138,0.18)]",
          "motion": "hover:-translate-y-[1px] active:translate-y-0 active:scale-[0.99]"
        },
        "secondary": {
          "usage": "Düzenle / Yeniden Dene",
          "tailwind": "bg-secondary text-foreground hover:bg-[#E9F1F7] border border-border",
          "motion": "hover:-translate-y-[1px]"
        },
        "ghost": {
          "usage": "Tablo filtre temizle, küçük aksiyonlar",
          "tailwind": "hover:bg-accent hover:text-foreground"
        },
        "destructive": {
          "usage": "Sil / İptal",
          "tailwind": "bg-[var(--brand-danger)] text-white hover:bg-[#8E1B13]"
        }
      },
      "sizes": {
        "sm": "h-9 px-3 text-sm",
        "md": "h-10 px-4",
        "lg": "h-11 px-5"
      },
      "data_testid_examples": [
        "scan-capture-button",
        "scan-extract-button",
        "scan-save-button",
        "bulk-next-scan-button",
        "guest-checkin-button",
        "guest-checkout-button",
        "table-filter-reset-button"
      ]
    },

    "status_badges": {
      "pattern": "Use <Badge> with soft background + colored left dot.",
      "chip_classes": {
        "checked_in": "bg-[var(--brand-success-soft)] text-[var(--brand-success)] border border-[#A7F3D0]",
        "checked_out": "bg-[var(--brand-sky-soft)] text-[var(--brand-info)] border border-[#BFDBFE]",
        "pending": "bg-[var(--brand-warning-soft)] text-[var(--brand-warning)] border border-[#FED7AA]",
        "issue": "bg-[var(--brand-danger-soft)] text-[var(--brand-danger)] border border-[#FECDD3]"
      },
      "data_testid_examples": ["guest-status-chip", "scan-status-chip"]
    },

    "tables_and_filters": {
      "table_header": "Sticky header row; include column sorting affordance (icon + hover).",
      "filter_bar": {
        "layout": "flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between",
        "left": "Search input with leading icon + status chip group (Tabs or ToggleGroup)",
        "right": "Date range (Popover+Calendar) + nationality Select + export button"
      },
      "recommended_components": ["Input", "Tabs", "ToggleGroup", "Select", "Popover", "Calendar", "Table", "Pagination"],
      "data_testid_examples": [
        "guest-search-input",
        "history-search-input",
        "status-filter-tabs",
        "date-filter-popover",
        "nationality-filter-select",
        "guest-table",
        "scan-history-table"
      ]
    },

    "scan_camera_module": {
      "camera_card": {
        "container": "Card with p-3 sm:p-4; solid white",
        "preview": "Use AspectRatio; overlay corners + guidance text; show permission states",
        "overlay": "Four corner brackets + center line for MRZ (passport)"
      },
      "actions": [
        "Primary: Yakala",
        "Secondary: Yeniden Dene",
        "Tertiary: Flaş (if supported), Kamera değiştir"
      ],
      "review": "After capture: show captured image thumbnail strip; allow rotate/crop ONLY if later needed; keep MVP minimal.",
      "data_testid_examples": [
        "camera-live-preview",
        "camera-permission-alert",
        "camera-switch-button",
        "camera-capture-button",
        "capture-thumbnail"
      ]
    },

    "extraction_form": {
      "structure": "Card -> Form sections: Kimlik Bilgileri, Belge Bilgileri, Misafir Durumu",
      "fields": [
        "Ad",
        "Soyad",
        "TCKN / Pasaport No",
        "Doğum Tarihi (Calendar)",
        "Cinsiyet (Select)",
        "Uyruk (Select)",
        "Belge Türü (Select)",
        "Not (Textarea, optional)"
      ],
      "confidence_ui": "If backend returns confidence: show subtle progress bar per field; else show a single 'AI okuma' info row.",
      "inline_edit": "Always editable inputs; highlight changed fields with a small 'Düzenlendi' badge.",
      "data_testid_examples": [
        "guest-first-name-input",
        "guest-last-name-input",
        "guest-document-number-input",
        "guest-birthdate-calendar",
        "guest-gender-select",
        "guest-nationality-select",
        "guest-document-type-select",
        "extraction-confidence-row"
      ]
    }
  },

  "page_blueprints": {
    "app_shell": {
      "nav": {
        "type": "Left sidebar (desktop) + Sheet drawer (tablet)",
        "items_tr": ["Genel Bakış", "Tara", "Toplu Tarama", "Misafirler", "Geçmiş"],
        "footer": "User/profile + 'Ayarlar' placeholder",
        "data_testid": ["sidebar-nav", "mobile-nav-sheet-trigger"]
      },
      "topbar": {
        "elements": ["Global search (optional)", "Hotel selector (future)", "Help"],
        "right_actions": ["Yeni Tarama" CTA button],
        "data_testid": ["topbar", "topbar-new-scan-button"]
      }
    },

    "dashboard": {
      "kpis": [
        {"title": "Bugün Check-in", "icon": "LogIn", "value": "24"},
        {"title": "Bugün Check-out", "icon": "LogOut", "value": "18"},
        {"title": "Toplam Misafir", "icon": "Users", "value": "3.214"},
        {"title": "İnceleme Bekleyen", "icon": "ShieldCheck", "value": "2"}
      ],
      "secondary_panels": [
        "Son Taramalar (Scan History mini table)",
        "Bugünkü İşlemler (check-in/out queue)",
        "Hızlı Tarama CTA card"
      ],
      "chart": {
        "library": "recharts",
        "use": "Last 7 days check-ins line chart (tiny, non-dominant).",
        "install": "npm i recharts",
        "data_testid": "dashboard-checkins-chart"
      }
    },

    "scan_page": {
      "flow": [
        "1) Kamera Açık (izin durumu)",
        "2) Yakala",
        "3) AI Çıkarım (yükleniyor skeleton)",
        "4) Formu kontrol et / düzenle",
        "5) Kaydet (sonner toast + redirect to guest detail)"
      ],
      "empty_states": {
        "no_camera": "Kamera erişimi verilemedi. Tarayıcı izinlerini kontrol edin.",
        "no_capture_yet": "Belgeyi çerçeveye hizalayın ve 'Yakala'ya basın."
      }
    },

    "bulk_scan": {
      "ux": "Persistent counter + guest queue rail. After save, auto-return to camera. Provide 'Geri Al' for last item.",
      "components": ["Progress", "Card", "Table"],
      "data_testid": ["bulk-scan-counter", "bulk-scan-queue-table", "bulk-scan-undo-button"]
    },

    "guest_list_history": {
      "table_columns": ["Ad Soyad", "Belge", "Uyruk", "Durum", "Son Tarama", "İşlem"],
      "row_actions": ["Detay", "Check-in", "Check-out"],
      "filters": ["Durum", "Tarih", "Uyruk", "Belge Türü"],
      "data_testid": ["guest-list-page", "guest-row-actions-menu"]
    },

    "guest_detail": {
      "layout": "Two-column on desktop: Profile card + Timeline card. Single-column on tablet.",
      "timeline": "Use Accordion or simple list with timestamp, scan thumbnail, extracted fields diff.",
      "actions": ["Düzenle", "Yeni Tarama", "Check-in", "Check-out"],
      "data_testid": ["guest-detail-page", "guest-scan-timeline"]
    }
  },

  "motion_and_microinteractions": {
    "principles": [
      "Fast, minimal motion: 120-180ms for hovers; 180-240ms for dialogs/drawers",
      "Prefer opacity/translateY; avoid layout-shift animations",
      "No universal transition: never `transition-all`"
    ],
    "scan_feedback": [
      "Capture button: subtle press scale 0.99",
      "After capture: quick flash overlay (opacity 0 -> 0.15 -> 0) 120ms",
      "Extraction loading: skeleton lines + spinner in button"
    ],
    "table_feedback": [
      "Row hover: bg-secondary",
      "Selected row: left border highlight 2px in primary",
      "Filter chip toggle: small slide underline"
    ],
    "optional_library": {
      "framer_motion": {
        "why": "Animate page transitions + timeline entries without heavy CSS.",
        "install": "npm i framer-motion",
        "usage": "Wrap main content with motion.div (opacity + y)."
      }
    }
  },

  "accessibility_and_security_ui": {
    "a11y": [
      "WCAG AA contrast on text/buttons",
      "Visible focus state using ring",
      "Keyboard navigation: tables, menus, dialogs",
      "Use labels for all inputs"
    ],
    "privacy_copy_tr": {
      "banner": "Kimlik verileri yalnızca konaklama işlemleri için işlenir.",
      "consent": "Kişisel verilerin işlenmesini onaylıyorum (KVKK)."
    },
    "audit_trust": [
      "Show 'Son tarama' timestamp",
      "Show operator name (future) and device (optional)"
    ],
    "data_testid_note": "All interactive and key informational elements MUST have data-testid. Use kebab-case role-based naming."
  },

  "image_urls": {
    "brand_context": [
      {
        "category": "dashboard-header",
        "description": "Optional small header illustration/photo thumbnail (keep subtle).",
        "url": "https://images.pexels.com/photos/32978233/pexels-photo-32978233.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940"
      }
    ],
    "empty_states": [
      {
        "category": "scan-empty-state",
        "description": "Use as a tiny illustration in empty state cards (optional).",
        "url": "https://images.unsplash.com/photo-1659035260002-11d486d6e9f5?crop=entropy&cs=srgb&fm=jpg&ixlib=rb-4.1.0&q=85"
      }
    ]
  },

  "instructions_to_main_agent": {
    "global_css_cleanup": [
      "Remove CRA demo styles in /app/frontend/src/App.css (App-header centering/dark background). Keep file minimal.",
      "Set global fonts in index.css using Google Fonts import (Space Grotesk + Inter).",
      "Update :root HSL tokens to match design_tokens.css_custom_properties.base.",
      "Keep background white; cards solid white; no transparent backgrounds."
    ],
    "navigation_structure": [
      "Create AppShell layout with Sidebar + Topbar.",
      "Use Sheet for mobile/tablet nav.",
      "All nav links/buttons must include data-testid." 
    ],
    "scan_page_implementation_notes": [
      "Use MediaDevices getUserMedia for preview; show permission alert state.",
      "On capture: draw video frame to canvas, store blob, show preview.",
      "After GPT extraction: populate form inputs; allow manual edits; show Sonner toast on save."
    ],
    "table_design_notes": [
      "Use shadcn Table with sticky header container; add filter bar above.",
      "Use Badge for statuses with soft backgrounds.",
      "Ensure table is usable on tablet: horizontal scroll + sticky actions." 
    ],
    "libraries": [
      {"name": "recharts", "install": "npm i recharts", "usage": "Light dashboard chart"},
      {"name": "framer-motion (optional)", "install": "npm i framer-motion", "usage": "Micro motion + page transitions"}
    ]
  }
}

<General UI UX Design Guidelines>  
    - You must **not** apply universal transition. Eg: `transition: all`. This results in breaking transforms. Always add transitions for specific interactive elements like button, input excluding transforms
    - You must **not** center align the app container, ie do not add `.App { text-align: center; }` in the css file. This disrupts the human natural reading flow of text
   - NEVER: use AI assistant Emoji characters like`🤖🧠💭💡🔮🎯📚🎭🎬🎪🎉🎊🎁🎀🎂🍰🎈🎨🎰💰💵💳🏦💎🪙💸🤑📊📈📉💹🔢🏆🥇 etc for icons. Always use **FontAwesome cdn** or **lucid-react** library already installed in the package.json

 **GRADIENT RESTRICTION RULE**
NEVER use dark/saturated gradient combos (e.g., purple/pink) on any UI element.  Prohibited gradients: blue-500 to purple 600, purple 500 to pink-500, green-500 to blue-500, red to pink etc
NEVER use dark gradients for logo, testimonial, footer etc
NEVER let gradients cover more than 20% of the viewport.
NEVER apply gradients to text-heavy content or reading areas.
NEVER use gradients on small UI elements (<100px width).
NEVER stack multiple gradient layers in the same viewport.

**ENFORCEMENT RULE:**
    • Id gradient area exceeds 20% of viewport OR affects readability, **THEN** use solid colors

**How and where to use:**
   • Section backgrounds (not content backgrounds)
   • Hero section header content. Eg: dark to light to dark color
   • Decorative overlays and accent elements only
   • Hero section with 2-3 mild color
   • Gradients creation can be done for any angle say horizontal, vertical or diagonal

- For AI chat, voice application, **do not use purple color. Use color like light green, ocean blue, peach orange etc**

</Font Guidelines>

- Every interaction needs micro-animations - hover states, transitions, parallax effects, and entrance animations. Static = dead. 
   
- Use 2-3x more spacing than feels comfortable. Cramped designs look cheap.

- Subtle grain textures, noise overlays, custom cursors, selection states, and loading animations: separates good from extraordinary.
   
- Before generating UI, infer the visual style from the problem statement (palette, contrast, mood, motion) and immediately instantiate it by setting global design tokens (primary, secondary/accent, background, foreground, ring, state colors), rather than relying on any library defaults. Don't make the background dark as a default step, always understand problem first and define colors accordingly
    Eg: - if it implies playful/energetic, choose a colorful scheme
           - if it implies monochrome/minimal, choose a black–white/neutral scheme

**Component Reuse:**
	- Prioritize using pre-existing components from src/components/ui when applicable
	- Create new components that match the style and conventions of existing components when needed
	- Examine existing components to understand the project's component patterns before creating new ones

**IMPORTANT**: Do not use HTML based component like dropdown, calendar, toast etc. You **MUST** always use `/app/frontend/src/components/ui/ ` only as a primary components as these are modern and stylish component

**Best Practices:**
	- Use Shadcn/UI as the primary component library for consistency and accessibility
	- Import path: ./components/[component-name]

**Export Conventions:**
	- Components MUST use named exports (export const ComponentName = ...)
	- Pages MUST use default exports (export default function PageName() {...})

**Toasts:**
  - Use `sonner` for toasts"
  - Sonner component are located in `/app/src/components/ui/sonner.tsx`

Use 2–4 color gradients, subtle textures/noise overlays, or CSS-based noise to avoid flat visuals.
</General UI UX Design Guidelines>
