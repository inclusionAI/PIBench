@php
    /** @var string $gymName */
    /** @var string|null $gymEmail */
    /** @var string|null $gymContact */
@endphp

<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="font-family: Arial, sans-serif; background: #f6f7fb; padding: 24px 0;">
    <tr>
        <td align="center">
            <table role="presentation" width="640" cellpadding="0" cellspacing="0" style="background: #ffffff; border: 1px solid #e5e7eb;">
                <tr>
                    <td style="padding: 20px 22px; background: #0b152d; color: #ffffff;">
                        <div style="font-size: 18px; font-weight: 700; line-height: 1.2;">{{ $gymName }}</div>
                        <div style="font-size: 12px; color: #cbd5e1; margin-top: 6px;">
                            @if (filled($gymEmail))
                                {{ $gymEmail }}
                            @endif
                            @if (filled($gymEmail) && filled($gymContact))
                                &nbsp;|&nbsp;
                            @endif
                            @if (filled($gymContact))
                                {{ $gymContact }}
                            @endif
                        </div>
                    </td>
                </tr>

                <tr>
                    <td style="padding: 22px;">
                        @yield('content')
                    </td>
                </tr>

                <tr>
                    <td style="padding: 14px 22px; background: #f9fafb; font-size: 11px; color: #6b7280;">
                        Sent by {{ $gymName }} via Gymie.
                    </td>
                </tr>
            </table>
        </td>
    </tr>
</table>

