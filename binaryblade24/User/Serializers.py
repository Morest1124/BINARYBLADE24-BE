from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist
from django.utils.encoding import force_str
# Prefer importing the concrete User class from local models so static analyzers
# and type checkers know about custom fields like `roles`.
from .models import Profile, Role, NotificationPreferences, UserPreferences
try:
    from .models import User
except Exception:
    # Fallback to get_user_model at runtime if direct import isn't possible
    User = get_user_model()
from django.contrib.auth.hashers import make_password
from django.db.models import Avg

# from Project.models import Project # Moved inside methods to avoid circular dependency
# from Review.models import Review # Moved inside methods to avoid circular dependency

class CaseInsensitiveSlugRelatedField(serializers.SlugRelatedField):
    def to_internal_value(self, data):
        try:
            # Perform a case-insensitive lookup
            return self.get_queryset().get(**{f'{self.slug_field}__iexact': data})
        except ObjectDoesNotExist:
            # Use force_str for robust error messaging
            self.fail('does_not_exist', slug_name=self.slug_field, value=force_str(data))
        except (TypeError, ValueError):
            self.fail('invalid')

# Ensure User is the concrete custom User model (imported above)
class FreelancerDetailSerializer(serializers.ModelSerializer):
    """
    Minimal serializer for User details, used for nesting.
    """
    avg_rating = serializers.SerializerMethodField(read_only=True)
    
    class Meta:
        model = User
        fields = ['id', 'username', 'first_name', 'last_name', 'avg_rating', 'profile_picture']

    def get_avg_rating(self, obj):
        """Get average rating from user profile."""
        from Review.models import Review
        try:
            # Aggregate from Review model
            agg = Review.objects.filter(reviewee=obj).aggregate(avg=Avg('rating'))
            avg = agg.get('avg')
            if avg is not None:
                return round(avg, 1)
            
            # Fallback to profile rating if review aggregation yields nothing
            # Note: Accessing obj.profile might fail if there's a schema mismatch (e.g. missing wallet_balance)
            return getattr(obj.profile, 'rating', 0.0) if hasattr(obj, 'profile') else 0.0
            
        except (ObjectDoesNotExist, Exception):
            # Exception caught here includes OperationalError (missing columns)
            return 0.0

class UserContactSerializer(serializers.ModelSerializer):
    """
    Serializer exposing contact details, used when an agreement is reached.
    """
    class Meta:
        model = User
        fields = ['id', 'username', 'first_name', 'last_name', 'email', 'phone_number']

class ProfileSerializer(serializers.ModelSerializer):
    # Computed/read-only fields
    completed_projects = serializers.SerializerMethodField(read_only=True)
    portfolio = serializers.SerializerMethodField(read_only=True)
    active_projects = serializers.SerializerMethodField(read_only=True)
    projects_posted = serializers.SerializerMethodField(read_only=True)
    avg_rating = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Profile
        # include profile editable fields plus computed read-only fields
        fields = (
            'bio', 'address', 'skills', 'hourly_rate', 'rating', 'level', 'availability',
            'completed_projects', 'portfolio', 'active_projects', 'projects_posted', 'avg_rating'
        )

        read_only_fields = ('completed_projects', 'portfolio', 'active_projects', 'projects_posted', 'avg_rating')

    def get_completed_projects(self, obj):
        """Return a list of minimal completed project info for this user's created projects."""
        from Project.models import Project
        projects = Project.objects.filter(client=obj.user, status=Project.ProjectStatus.COMPLETED)
        result = []
        for p in projects:
            result.append({
                'id': p.id,
                'title': p.title,
                'thumbnail': p.thumbnail.url if p.thumbnail else None,
                'status': p.status,
            })
        return result

    def get_portfolio(self, obj):
        """Return a list of thumbnail URLs from completed projects (portfolio)."""
        from Project.models import Project
        projects = Project.objects.filter(client=obj.user, status=Project.ProjectStatus.COMPLETED).exclude(thumbnail='')
        thumbs = [p.thumbnail.url for p in projects if p.thumbnail]
        return thumbs

    def get_active_projects(self, obj):
        from Project.models import Project
        projects = Project.objects.filter(client=obj.user, status=Project.ProjectStatus.IN_PROGRESS)
        return [{'id': p.id, 'title': p.title, 'status': p.status} for p in projects]

    def get_projects_posted(self, obj):
        from Project.models import Project
        return Project.objects.filter(client=obj.user).count()

    def get_avg_rating(self, obj):
        from Review.models import Review
        # Prefer calculating from Review model; fall back to stored profile.rating
        agg = Review.objects.filter(reviewee=obj.user).aggregate(avg=Avg('rating'))
        avg = agg.get('avg')
        if avg is None:
            return obj.rating
        # round to one decimal for presentation
        return round(avg, 1)


class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False, min_length=8)
    profile = ProfileSerializer(required=False)
    roles = CaseInsensitiveSlugRelatedField(
        many=True,
        slug_field='name',
        queryset=Role.objects.all(),
        required=False
    )
    profile_picture = serializers.ImageField(required=False, allow_null=True)

    class Meta:
        model = User
        fields = ('id', 'username', 'first_name', 'last_name', 'email', 'password', 'profile', 'identity_number', 'profile_picture', 'roles', 'date_joined', 'last_login', 'country_origin', 'phone_number', 'phone_country_code', 'is_email_verified')
        read_only_fields = ('id', 'date_joined', 'last_login', 'is_email_verified')



    def create(self, validated_data):
        profile_data = validated_data.pop('profile', None)
        password = validated_data.pop('password')
        roles_data = validated_data.pop('roles')

        # Convert Role objects to a set of role names for easier lookup.
        # The names will be in the case they are stored in the DB ('FREELANCER').
        role_names = {role.name for role in roles_data}

        # If 'FREELANCER' is one of the chosen roles, automatically add 'CLIENT'
        if 'FREELANCER' in role_names:
            client_role, created = Role.objects.get_or_create(name='CLIENT')
            # Add the client role object to the list for setting the relationship
            if client_role not in roles_data:
                roles_data.append(client_role)

        if 'identity_number' in validated_data:
            validated_data['identity_number'] = make_password(validated_data['identity_number'])
        user = User.objects.create_user(password=password, **validated_data)
        
        # roles is a custom ManyToMany on the concrete User model; static type
        user.roles.set(roles_data)  # type: ignore[attr-defined]
        # The post_save signal already created a profile.
        if profile_data:
            # user.profile is available thanks to the OneToOneField relation
            profile = user.profile
            for key, value in profile_data.items():
                setattr(profile, key, value)
            profile.save()
        return user

    def update(self, instance, validated_data):
        if 'password' in validated_data:
            password = validated_data.pop('password')
            instance.set_password(password)

        if 'identity_number' in validated_data:
            new_identity_number = validated_data.pop('identity_number')
            #(Suggested by Gemini)
            # Only hash if the new identity number is different and doesn't look already hashed
            # This is a heuristic; a more robust solution might involve a separate endpoint
            # or a clear distinction between plain and hashed values.
            if new_identity_number != instance.identity_number and not new_identity_number.startswith(('pbkdf2_sha256$', 'bcrypt$', 'sha1$')):
                instance.identity_number = make_password(new_identity_number)
            elif new_identity_number != instance.identity_number: # If it's different and already hashed, assume it's a valid pre-hashed value
                instance.identity_number = new_identity_number

        profile_data = validated_data.pop('profile', None)
        if profile_data:
            profile = instance.profile
            for attr, value in profile_data.items():
                setattr(profile, attr, value)
            profile.save()

        if 'roles' in validated_data:
            roles_data = validated_data.pop('roles')
            # Check for dual role requirement in update as well
            role_names = {role.name for role in roles_data}
            if 'FREELANCER' in role_names:
                client_role, created = Role.objects.get_or_create(name='CLIENT')
                if client_role not in roles_data:
                    # Convert to list if it's a queryset/set to allow append/extend
                    roles_list = list(roles_data)
                    roles_list.append(client_role)
                    roles_data = roles_list
            instance.roles.set(roles_data)  # type: ignore[attr-defined]

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        instance.save()
        return instance

class NotificationPreferencesSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationPreferences
        fields = [
            'email_new_message', 'email_payment_received', 
            'email_proposal_submitted', 'email_system_updates',
            'push_notifications', 'marketing_emails'
        ]


class UserPreferencesSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserPreferences
        fields = ['language', 'timezone', 'preferred_currency', 'dark_mode', 'default_view']


class PublicUserProfileSerializer(serializers.ModelSerializer):
    """
    Safe public profile serializer — no sensitive data.
    Used for the public /users/<pk>/public/ endpoint (AllowAny).
    For freelancers, shows GIG projects they created, active projects, and portfolio thumbnails.
    """
    bio = serializers.SerializerMethodField()
    skills = serializers.SerializerMethodField()
    hourly_rate = serializers.SerializerMethodField()
    level = serializers.SerializerMethodField()
    availability = serializers.SerializerMethodField()
    avg_rating = serializers.SerializerMethodField()
    roles = serializers.SerializerMethodField()
    profile_picture = serializers.SerializerMethodField()
    completed_projects = serializers.SerializerMethodField()
    active_projects = serializers.SerializerMethodField()
    active_projects_count = serializers.SerializerMethodField()
    portfolio = serializers.SerializerMethodField()
    total_projects_created = serializers.SerializerMethodField()
    total_earnings = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'username', 'first_name', 'last_name', 'date_joined',
            'country_origin', 'profile_picture',
            'bio', 'skills', 'hourly_rate', 'level', 'availability', 'avg_rating',
            'roles',
            'completed_projects', 'active_projects', 'active_projects_count',
            'portfolio', 'total_projects_created', 'total_earnings',
        ]

    def _get_profile(self, obj):
        try:
            return obj.profile
        except Exception:
            return None

    def get_profile_picture(self, obj):
        request = self.context.get('request')
        if obj.profile_picture:
            url = obj.profile_picture.url
            if request:
                return request.build_absolute_uri(url)
            return url
        return None

    def get_bio(self, obj):
        p = self._get_profile(obj)
        return p.bio if p else None

    def get_skills(self, obj):
        p = self._get_profile(obj)
        return p.skills if p else None

    def get_hourly_rate(self, obj):
        p = self._get_profile(obj)
        return str(p.hourly_rate) if p and p.hourly_rate else None

    def get_level(self, obj):
        p = self._get_profile(obj)
        return p.level if p else None

    def get_availability(self, obj):
        p = self._get_profile(obj)
        return p.availability if p else None

    def get_avg_rating(self, obj):
        from Review.models import Review
        from django.db.models import Avg
        agg = Review.objects.filter(reviewee=obj).aggregate(avg=Avg('rating'))
        avg = agg.get('avg')
        if avg is not None:
            return round(avg, 1)
        p = self._get_profile(obj)
        return float(p.rating) if p and p.rating else 0.0

    def get_roles(self, obj):
        return list(obj.roles.values_list('name', flat=True))

    def _is_freelancer(self, obj):
        return obj.roles.filter(name__iexact='freelancer').exists()

    def get_completed_projects(self, obj):
        """Projects created by this user (as GIGs) that are COMPLETED."""
        from Project.models import Project
        request = self.context.get('request')
        qs = Project.objects.filter(
            client=obj,
            status=Project.ProjectStatus.COMPLETED
        ).order_by('-updated_at')[:12]
        result = []
        for p in qs:
            thumb = None
            if p.thumbnail:
                url = p.thumbnail.url
                thumb = request.build_absolute_uri(url) if request else url
            result.append({
                'id': p.id,
                'title': p.title,
                'thumbnail': thumb,
                'project_type': p.project_type,
            })
        return result

    def get_active_projects(self, obj):
        """Projects created by this user that are IN_PROGRESS."""
        from Project.models import Project
        qs = Project.objects.filter(
            client=obj,
            status=Project.ProjectStatus.IN_PROGRESS
        ).order_by('-updated_at')[:6]
        return [{'id': p.id, 'title': p.title, 'project_type': p.project_type} for p in qs]

    def get_active_projects_count(self, obj):
        from Project.models import Project
        return Project.objects.filter(client=obj, status=Project.ProjectStatus.IN_PROGRESS).count()

    def get_portfolio(self, obj):
        """Thumbnails from completed projects created by this user."""
        from Project.models import Project
        request = self.context.get('request')
        qs = Project.objects.filter(
            client=obj,
            status=Project.ProjectStatus.COMPLETED
        ).exclude(thumbnail='').exclude(thumbnail=None).order_by('-updated_at')[:12]
        result = []
        for p in qs:
            if p.thumbnail:
                url = p.thumbnail.url
                result.append(request.build_absolute_uri(url) if request else url)
        return result

    def get_total_projects_created(self, obj):
        from Project.models import Project
        return Project.objects.filter(client=obj).count()

    def get_total_earnings(self, obj):
        """Calculate total earnings from completed order items."""
        from Order.models import OrderItem
        from django.db.models import Sum
        return OrderItem.objects.filter(
            freelancer=obj,
            order__status='COMPLETED'
        ).aggregate(total=Sum('final_price'))['total'] or 0.0
