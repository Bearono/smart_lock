// Semi-implicit integration, substepped so refresh rate and short frame stalls
// do not change the feel or destabilize the spring.
export function advanceSpring(state, target, elapsed) {
  const time = Math.min(Math.max(elapsed, 0), 0.064)
  const steps = Math.max(1, Math.ceil(time / (1 / 120)))
  const dt = time / steps
  let { position, velocity } = state
  for (let i = 0; i < steps; i++) {
    velocity += (360 * (target - position) - 22 * velocity) * dt
    position += velocity * dt
  }
  return { position, velocity }
}

export function springSettled(state, target) {
  return Math.abs(state.position - target) < 0.0002 && Math.abs(state.velocity) < 0.002
}
