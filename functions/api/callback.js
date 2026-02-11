export async function onRequestGet(context) {
  const { searchParams } = new URL(context.request.url);
  const code = searchParams.get('code');

  if (!code) {
    return new Response('Missing code parameter', { status: 400 });
  }

  const clientId = context.env.GITHUB_CLIENT_ID;
  const clientSecret = context.env.GITHUB_CLIENT_SECRET;

  if (!clientId || !clientSecret) {
    return new Response('OAuth credentials not configured', { status: 500 });
  }

  try {
    const tokenResponse = await fetch('https://github.com/login/oauth/access_token', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
      },
      body: JSON.stringify({
        client_id: clientId,
        client_secret: clientSecret,
        code,
      }),
    });

    const data = await tokenResponse.json();

    if (data.error) {
      return new Response(`OAuth error: ${data.error_description || data.error}`, { status: 400 });
    }

    const content = JSON.stringify({
      token: data.access_token,
      provider: 'github',
    });

    return new Response(
      `<!DOCTYPE html>
<html>
<head><title>Authorizing...</title></head>
<body>
<script>
(function() {
  var token = ${content};
  var opener = window.opener;

  function sendMessage(e) {
    opener.postMessage(
      'authorization:github:success:' + JSON.stringify(token),
      e.origin
    );
  }

  window.addEventListener('message', sendMessage, false);
  opener.postMessage('authorizing:github', '*');
})();
</script>
</body>
</html>`,
      {
        status: 200,
        headers: { 'Content-Type': 'text/html;charset=UTF-8' },
      }
    );
  } catch (error) {
    return new Response(`Authentication failed: ${error.message}`, { status: 500 });
  }
}
