// Keep issued credentials until consumption succeeds, so network failures can be retried.
export async function consumeDoorToken(credential, consume, queryOutcome) {
  if (!credential?.unlock_token || !credential?.device_id) {
    throw new Error('Missing unlock credential; start authentication again')
  }
  let response
  try {
    response = await consume(credential.unlock_token, credential.device_id)
  } catch (error) {
    // A lost response is ambiguous. Recover the original receipt without issuing
    // a second command or consuming another guest allowance.
    if (queryOutcome) {
      try {
        const outcome = await queryOutcome(credential.unlock_token, credential.device_id)
        if (outcome.data?.id)
          return { ...outcome.data, command_id: outcome.data.id, command_accepted: true }
      } catch {
        /* Preserve the original actionable error. */
      }
    }
    throw error
  }
  if (response.data?.command_accepted !== true) {
    throw new Error('The backend did not acknowledge the unlock command')
  }
  return response.data
}
