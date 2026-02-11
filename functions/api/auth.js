export async function onRequestGet(context) {
  const clientId = context.env.GITHUB_CLIENT_ID;

  if (!clientId) {
    return new Response('GITHUB_CLIENT_ID not configured', { status: 500 });
  }

  const redirectUrl = new URL('https://github.com/login/oauth/authorize');
  redirectUrl.searchParams.set('client_id', clientId);
  redirectUrl.searchParams.set('scope', 'repo,user');

  return Response.redirect(redirectUrl.toString(), 302);
}
