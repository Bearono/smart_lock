// Keep issued credentials until consumption succeeds, so network failures can be retried.
export async function consumeDoorToken(credential, consume) {
  if (!credential?.unlock_token || !credential?.device_id) {
    throw new Error('Missing unlock credential; start authentication again')
  }
  const response = await consume(credential.unlock_token, credential.device_id)
  if (response.data?.command_accepted !== true) {
    throw new Error('The backend did not acknowledge the unlock command')
  }
  return response.data
}
