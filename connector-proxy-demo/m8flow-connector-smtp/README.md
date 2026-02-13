# M8Flow Connector SMTP

The M8Flow Connector SMTP provides email-sending capabilities through an SMTP server. It is designed for use within BPMN Service Tasks and supports both  authenticated and unauthenticated SMTP configurations.

## Supported Features

The following capabilities are supported:

- Support for `CC`, `BCC`, and `Reply-To` headers
- Plain text and HTML email body
- SMTP authentication (username and password)
- Optional TLS / STARTTLS encryption
- File attachment support

## Attachment Support

Attachments may be provided in two supported formats:

1. Base64-encoded content
    - The file content is transmitted directly as Base64.
    - The filename and MIME type must be provided.
2. Filesystem path reference
    - The file path must be restricted to the directory defined by the environment variable: `M8FLOW_CONNECTOR_SMTP_ATTACHMENTS_FOLDER`
    - This restriction is enforced to prevent unauthorized access to arbitrary filesystem locations.

This design ensures that attachments are handled in a controlled and secure manner within containerized deployments.

## Security Considerations

- Credentials should not be hardcoded in BPMN models.
- Sensitive data should be provided through secure environment variables or secrets management mechanisms.
- TLS encryption should be enabled whenever supported by the SMTP server.
