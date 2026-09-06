import * as React from "react"

const MOBILE_BREAKPOINT = 768

const isMobileWidth = () => window.innerWidth < MOBILE_BREAKPOINT

export function useIsMobile() {
  // A single-page app in a browser: the width is known on the first render, so the state
  // starts from it and the effect only follows later changes.
  const [isMobile, setIsMobile] = React.useState(isMobileWidth)

  React.useEffect(() => {
    const mql = window.matchMedia(`(max-width: ${MOBILE_BREAKPOINT - 1}px)`)
    const onChange = () => setIsMobile(isMobileWidth())
    mql.addEventListener("change", onChange)
    return () => mql.removeEventListener("change", onChange)
  }, [])

  return isMobile
}
