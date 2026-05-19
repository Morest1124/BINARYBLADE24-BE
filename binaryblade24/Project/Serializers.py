from rest_framework import serializers
from .models import Project, Category, Milestone 
from django.contrib.auth import get_user_model

User = get_user_model()




# Project Management Serializers
class CategorySerializer(serializers.ModelSerializer):
    """Serializer for Project Categories."""
    class Meta:
        model = Category
        fields = '__all__'
        read_only_fields = ['id', 'slug']

class ProjectSerializer(serializers.ModelSerializer):
    """Main serializer for Project CRUD operations."""
    # Nested field to display the client's public username
    client_details = serializers.SerializerMethodField(read_only=True)
    
    # Aliases for semantic correctness in Gig model (Freelancer owns the Gig)
    owner = serializers.PrimaryKeyRelatedField(source='client', read_only=True)
    owner_details = serializers.SerializerMethodField(read_only=True)
    
    # Nested field to display the category name
    category_details = CategorySerializer(source='category', read_only=True)

    # Computed fields for ratings
    average_rating = serializers.SerializerMethodField()
    review_count = serializers.SerializerMethodField()
    view_count = serializers.SerializerMethodField()
    user_has_submitted = serializers.SerializerMethodField()

    class Meta:
        model = Project
        # Explicitly listing fields for security and output control
        fields = [
            'id', 
            'title', 
            'description', 
            'budget',
            'price',
            'category', 
            'status', 
            'client', 
            'owner', # Alias for client (freelancer in Gig model)
            'created_at', 
            'updated_at',
            'client_details',
            'owner_details', # Alias for client_details
            'category_details',
            'thumbnail',
            'delivery_days',
            'project_type',
            'average_rating',
            'review_count',
            'view_count',
            'user_has_submitted',
            # 'verbose_name',
            # 'help_text',
            
        ]
        
        # Security: Fields set by the server/view, not allowed in client input
        read_only_fields = [
            'id', 
            'client',
            'status',
            'created_at',
            'updated_at',
            'average_rating',
            'review_count',
            'view_count',
        ]

    def get_average_rating(self, obj):
        """Calculate average rating from related reviews."""
        reviews = obj.reviews.all()
        if not reviews.exists():
            return 0
        total = sum(r.rating for r in reviews)
        return round(total / reviews.count(), 1)

    def get_review_count(self, obj):
        """Return total number of reviews."""
        return obj.reviews.count()

    def get_view_count(self, obj):
        """Return total number of view impressions."""
        return obj.views.count()

    def get_user_has_submitted(self, obj):
        """Check if the current user has already submitted a proposal for this project."""
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.proposals.filter(freelancer=request.user).exists()
        return False

    def get_client_details(self, obj):
        """
        Return client public profile information.
        
        Returns basic client details without exposing contact information.
        All communication must happen through the platform messaging system.
        
        Args:
            obj (Project): The project instance being serialized
            
        Returns:
            dict: Serialized client data (public profile only)
            
        Business Rules:
            - Email/phone never exposed to maintain platform communication
            - Prevents freelancers from contacting clients off-platform
            - Protects platform revenue and user safety
        """
        from User.Serializers import FreelancerDetailSerializer
        
        # Always return minimal client details (no email/phone)
        return FreelancerDetailSerializer(obj.client).data

    def get_owner_details(self, obj):
        """Alias for get_client_details to support 'owner' semantic."""
        return self.get_client_details(obj)

# Proposal System Serializers

class ProjectNestedSerializer(serializers.ModelSerializer):
    """
    Minimal serializer to show the associated project title for Proposal output.
    """
    client_details = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Project
        fields = ['id', 'title', 'budget', 'client_details']

    def get_client_details(self, obj):
        from User.Serializers import FreelancerDetailSerializer
        return FreelancerDetailSerializer(obj.client).data



class MilestoneSerializer(serializers.ModelSerializer):
    """Serializer for Project Milestones."""
    class Meta:
        model = Milestone
        fields = ['id', 'project', 'title', 'description', 'amount', 'due_date', 'status', 'created_at']
        read_only_fields = ['id', 'project', 'status', 'created_at']

    def create(self, validated_data):
        # 1. Try to get project from the URL (nested route: /api/projects/<pk>/milestones/)
        project_id = self.context['view'].kwargs.get('project_pk')
        
        # 2. Try to get project from the request body if not in URL (standard route: /api/projects/milestones/)
        if not project_id:
            request = self.context.get('request')
            if request and 'project' in request.data:
                project_id = request.data.get('project')
        
        if project_id:
            validated_data['project_id'] = project_id
            
        return super().create(validated_data)
