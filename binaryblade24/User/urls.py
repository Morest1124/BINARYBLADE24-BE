from django.urls import path

app_name = 'User'
from .views import (
    LoginView,
    RegisterView, 
    UserListView, 
    UserDetailView, 
    LoginWithRoleView,
    UserProfileView,
    AddFreelancerRoleView,
    UserSearchView,
    UserSuggestionView,
    GlobalSearchView,
    SearchFilterOptionsView,
    PublicUserProfileView,
)
from .settings_views import (
    CountriesListView,
    ChangePasswordView,
    NotificationPreferencesView,
    UserPreferencesView,
    UserAccountView,
    TimezonesListView,
)
from .account_management_views import (
    DeactivateAccountView,
    ReactivateAccountView,
    RequestAccountDeletionView,
    CancelAccountDeletionView,
    AccountStatusView,
)
from Proposal.views import UserProposalsView
from Review.views import UserReviewsView
from .file_views import (
    FileUploadView,
    FileListView,
    FileDeleteView,
    FileDownloadView,
)
from .verification_views import (
    SendOTPView,
    VerifyOTPView,
    VerificationStatusView,
)

urlpatterns = [
    path('login/', LoginView.as_view(), name='login'),
    path('login/role/', LoginWithRoleView.as_view(), name='login_with_role'),
    path('register/', RegisterView.as_view(), name='register'),
    path('add-freelancer-role/', AddFreelancerRoleView.as_view(), name='add_freelancer_role'),
    path('users/', UserListView.as_view(), name='user-list'),
    path('users/<int:pk>/', UserDetailView.as_view(), name='user-detail'),
    path('users/<int:pk>/profile/', UserProfileView.as_view(), name='user-profile'),
    path('users/<int:pk>/public/', PublicUserProfileView.as_view(), name='user-public-profile'),
    path('users/<int:pk>/proposals/', UserProposalsView.as_view(), name='user-proposals'),
    path('users/<int:pk>/reviews/', UserReviewsView.as_view(), name='user-reviews'),
    
    # Search endpoints
    path('search/global/', GlobalSearchView.as_view(), name='global-search'),
    path('search/options/', SearchFilterOptionsView.as_view(), name='search-options'),
    path('search/suggest/', UserSuggestionView.as_view(), name='user-search-suggest'),
    
    # Stripe URLs
    # path('create-checkout-session/', StripeCheckoutView.as_view(), name='create-checkout-session'),
    # path('stripe-webhook/', stripe_webhook, name='stripe-webhook'),

    # PayPal URLs
    # path('payment/paypal/create/', CreatePayPalPaymentView.as_view(), name='paypal-create-payment'),
    # path('payment/paypal/execute/', ExecutePayPalPaymentView.as_view(), name='paypal-execute-payment'),
    
    # Settings endpoints
    path('settings/account/', UserAccountView.as_view(), name='settings-account'),
    path('settings/password/', ChangePasswordView.as_view(), name='settings-password'),
    path('settings/notifications/', NotificationPreferencesView.as_view(), name='settings-notifications'),
    path('settings/preferences/', UserPreferencesView.as_view(), name='settings-preferences'),
    path('countries/', CountriesListView.as_view(),name='countries-list'),
    path('timezones/', TimezonesListView.as_view(), name='timezones-list'),
    
    # Account management endpoints
    path('account/status/', AccountStatusView.as_view(), name='account-status'),
    path('account/deactivate/', DeactivateAccountView.as_view(), name='account-deactivate'),
    path('account/reactivate/', ReactivateAccountView.as_view(), name='account-reactivate'),
    path('account/delete/', RequestAccountDeletionView.as_view(), name='account-delete'),
    path('account/cancel-deletion/', CancelAccountDeletionView.as_view(), name='account-cancel-deletion'),
    
    # File management endpoints
    path('files/upload/', FileUploadView.as_view(), name='file-upload'),
    path('files/', FileListView.as_view(), name='file-list'),
    path('files/<int:pk>/delete/', FileDeleteView.as_view(), name='file-delete'),
    path('files/<int:pk>/download/', FileDownloadView.as_view(), name='file-download'),
    
    # Verification endpoints
    path('send-otp/', SendOTPView.as_view(), name='send-otp'),
    path('verify-otp/', VerifyOTPView.as_view(), name='verify-otp'),
    path('verification-status/', VerificationStatusView.as_view(), name='verification-status'),
]