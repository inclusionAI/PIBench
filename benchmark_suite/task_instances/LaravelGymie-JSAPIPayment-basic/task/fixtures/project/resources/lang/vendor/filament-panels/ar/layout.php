<?php

return [

    /**
     * Keep the Filament panel layout left-to-right even when the app locale is Arabic.
     *
     * This intentionally affects layout placement (sidebar, dropdowns, etc.) while
     * still allowing Arabic translations throughout the UI.
     */
    'direction' => 'ltr',

    'actions' => [

        'billing' => [
            'label' => 'إدارة الاشتراكات',
        ],

        'logout' => [
            'label' => 'تسجيل الخروج',
        ],

        'open_database_notifications' => [
            'label' => 'عرض التنبيهات',
        ],

        'open_user_menu' => [
            'label' => 'قائمة المستخدم',
        ],

        'sidebar' => [

            'collapse' => [
                'label' => 'طيّ القائمة الجانبية',
            ],

            'expand' => [
                'label' => 'توسيع القائمة الجانبية',
            ],

        ],

        'theme_switcher' => [

            'dark' => [
                'label' => 'تفعيل الوضع الليلي',
            ],

            'light' => [
                'label' => 'تفعيل الوضع النهاري',
            ],

            'system' => [
                'label' => 'تفعيل سمة النظام',
            ],

        ],

    ],

    'avatar' => [
        'alt' => 'صورة شخصية لـ :name',
    ],

    'logo' => [
        'alt' => ':name شعار',
    ],

    'tenant_menu' => [

        'search_field' => [
            'label' => 'البحث عن جهة',
            'placeholder' => 'بحث',
        ],

    ],

];

