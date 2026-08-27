---
version: alpha
name: AX Evaluation Console
description: A calm, structured education evaluation dashboard built with Bootstrap 5.3. The system prioritizes clear hierarchy, predictable interaction, compact Korean-first typography, and reusable layout patterns.
colors:
  primary: "#1769E0"
  primary-hover: "#0F5AC4"
  primary-container: "#EAF2FF"
  navigation: "#082A4B"
  navigation-hover: "#103A62"
  background: "#F6F8FC"
  surface: "#FFFFFF"
  surface-subtle: "#FAFBFD"
  text: "#182230"
  text-muted: "#667085"
  outline: "#E2E8F0"
  success: "#168A50"
  warning: "#B7791F"
  error: "#C93C3C"
typography:
  display:
    fontFamily: "Pretendard, Noto Sans KR, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif"
    fontSize: 28px
    fontWeight: 700
    lineHeight: 1.3
  heading:
    fontFamily: "Pretendard, Noto Sans KR, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif"
    fontSize: 18px
    fontWeight: 700
    lineHeight: 1.4
  body:
    fontFamily: "Pretendard, Noto Sans KR, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif"
    fontSize: 14px
    fontWeight: 400
    lineHeight: 1.6
  label:
    fontFamily: "Pretendard, Noto Sans KR, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif"
    fontSize: 13px
    fontWeight: 600
    lineHeight: 1.4
spacing:
  xs: 4px
  sm: 8px
  md: 16px
  lg: 24px
  xl: 32px
  xxl: 48px
rounded:
  sm: 6px
  md: 10px
  lg: 14px
layout:
  sidebar-width: 240px
  topbar-height: 64px
  content-max-width: 1440px
---

# AX Evaluation Console

## Overview

AX Evaluation Console is an education-focused evaluation system for students and tutors.

The interface should feel **calm, trustworthy, structured, and easy to scan**. It should look like a practical SaaS admin product rather than a promotional website.

The design should help users quickly understand where they are, what they need to do, what information is most important, and what action should come next.

Bootstrap 5.3 is the implementation baseline. Custom CSS should extend Bootstrap rather than replace its interaction model.

## Colors

The visual system uses a small, controlled palette.

- **Primary Blue** is the main interaction color.
- **Navigation Navy** anchors the application shell.
- **Light Gray Background** separates the canvas from content surfaces.
- **White Surface** is used for cards, tables, forms, and major content containers.
- **Neutral Text Colors** create clear hierarchy between primary and secondary information.
- **Semantic Colors** such as success, warning, and error are reserved for meaning rather than decoration.

Avoid introducing additional accent colors unless they have a clear functional purpose.

## Typography

Use a Korean-first system font stack so the interface remains stable without depending on an external web font.

Typography should remain compact and functional.

- Page titles establish the highest hierarchy.
- Section headings divide major content areas.
- Body text is optimized for dense dashboard information.
- Labels and controls use slightly stronger weight for quick scanning.

Avoid decorative fonts, oversized headings, or unnecessary text weight variation.

## Layout

The application uses a consistent dashboard shell.

### Desktop

- Fixed navigation sidebar on the left.
- Compact top bar above the main content area.
- Main content arranged with Bootstrap containers, rows, and columns.
- Content width should remain readable on large monitors.
- Cards and tables should align to a consistent grid.

### Tablet and Mobile

- The sidebar becomes a collapsible or off-canvas navigation.
- Multi-column layouts collapse progressively.
- Tables remain horizontally scrollable when necessary.
- Primary actions remain easy to reach and tap.

Do not compress information so aggressively that hierarchy or readability is lost.

## Spacing

Use a consistent 4px-based spacing rhythm.

Recommended spacing progression:

- 4px for micro spacing
- 8px for related inline elements
- 16px for standard component spacing
- 24px for sections and card padding
- 32px or more for major page separation

Spacing should communicate grouping before borders or decorative elements are added.

## Elevation & Depth

Use minimal elevation.

- The page canvas uses a light gray background.
- Content surfaces are white.
- Cards use a subtle border and restrained shadow.
- The top bar is separated with a border rather than a heavy shadow.
- The sidebar relies on color contrast rather than elevation.

Avoid glassmorphism, strong blur, deep shadows, or decorative layering.

## Shapes

Use restrained rounded corners.

- Small controls: subtle rounding
- Buttons and inputs: medium rounding
- Cards and major panels: slightly larger rounding

Rounded corners should remain consistent across the system.

Avoid exaggerated pill shapes except where the content naturally requires a compact inline control.

## Components

Bootstrap components should be used as the structural foundation.

Prefer:

- `container`, `container-fluid`
- `row`, `col-*`
- `card`
- `table`, `table-responsive`
- `btn`
- `form-control`, `form-check`, `form-select`
- `nav`, `navbar`, `offcanvas`
- spacing and responsive utility classes

Custom styling should focus on brand colors, spacing, radius, typography, navigation appearance, and overall visual consistency.

Feature-specific rules should live in the corresponding page or component implementation rather than in this document.

## Interaction

Interaction should remain predictable.

- One primary action should be visually dominant within each local context.
- Secondary actions should remain visually quieter.
- Destructive actions should be clearly separated.
- Disabled controls must still communicate why they are unavailable.
- Hover, focus, active, and disabled states should follow Bootstrap conventions.
- Important information should never depend on color alone.

Avoid custom interaction patterns when a standard Bootstrap pattern already communicates the same behavior clearly.

## Responsive Behavior

Responsive behavior should preserve information hierarchy rather than reproduce the desktop layout at a smaller size.

- Sidebar → off-canvas navigation
- Multi-column cards → fewer columns
- Wide tables → horizontal scrolling
- Dense action groups → stacked or wrapped controls
- Main content padding → reduced on smaller screens

Mobile layouts should remain task-oriented and readable.

## Accessibility

The UI should follow practical accessibility principles.

- Maintain sufficient text and control contrast.
- Use semantic HTML.
- Associate labels with form controls.
- Preserve keyboard focus states.
- Provide readable text for important states and actions.
- Keep interactive targets large enough for touch input.

Accessibility should be treated as part of the base design rather than an optional enhancement.

## Do's and Don'ts

### Do

- Use Bootstrap 5.3 as the default UI framework.
- Reuse the same layout and component language across pages.
- Keep the interface calm and information-focused.
- Use whitespace and hierarchy before adding decoration.
- Keep Korean UI labels short and literal.
- Prefer reusable patterns over page-specific visual inventions.
- Keep static HTML previews visually stable when opened independently.

### Don't

- Don't use decorative gradients across content surfaces.
- Don't use glassmorphism or heavy visual effects.
- Don't add multiple competing accent colors.
- Don't create different visual systems for each page.
- Don't override Bootstrap behavior unnecessarily.
- Don't encode feature-specific business rules into the global design specification.

---

## 부록 A — assignment-lms 적용 메모

이 문서는 AX Evaluator 팀에서 정의한 공용 디자인 시스템이며, 본 프로젝트(assignment-lms)도 동일하게 따른다.

- **CSS 토큰**: 위 front matter 의 `colors` / `typography` / `spacing` / `rounded` / `layout` 값을 `apps/common/static/common/css/` 에서 CSS 커스텀 프로퍼티(`--color-primary` 등)로 정의하고, 각 앱 CSS 는 이 변수만 참조한다.
- **Bootstrap 5.3**: CDN 대신 `apps/common/static/common/vendor/` 에 CSS/JS 를 넣는다. "static HTML preview 가 단독으로 열려도 안정적이어야 한다"는 원칙 때문.
- **폰트**: Pretendard/Noto Sans KR 는 시스템에 없을 수 있으므로 웹폰트를 강제하지 않는다. 폰트 스택의 시스템 폰트로 폴백되어도 레이아웃이 깨지지 않아야 한다.
- **의미 색상**: `success`(통과/완료), `warning`(마감 임박/지각), `error`(미제출/실패) 처럼 상태 표현에만 쓰고 장식으로 쓰지 않는다. 색만으로 의미를 전달하지 말고 라벨/아이콘을 병행한다 (예: "지각 제출" 배지, "평가 대기 중" 텍스트).
- 레이아웃 구조는 [LAYOUT.md](LAYOUT.md) 참고.
