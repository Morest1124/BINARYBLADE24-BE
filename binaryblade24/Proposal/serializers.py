"""
Proposal Serializers Module

This module contains serializers for handling proposal-related data transformations
and API representations in the BinaryBlade24 freelancing platform.

Key Features:
- Public profile information exposure only (no email/phone)
- Nested project information for proposal context
- Read-only bid amount (auto-populated from project budget)
- Platform-only communication enforcement

Author: BinaryBlade24 Team
Last Modified: 2025-11-27
"""

from rest_framework import serializers
from .models import Proposal
from Project.models import Project 
from django.contrib.auth import get_user_model

User = get_user_model()


class FreelancerDetailSerializer(serializers.ModelSerializer):
    """
    Minimal serializer for freelancer public profile information.
    
    This serializer exposes only basic, non-sensitive freelancer details
    that are safe to display to any authenticated user.
    
    Fields:
        id (int): Unique user identifier
        username (str): Public username
        first_name (str): Freelancer's first name
        last_name (str): Freelancer's last name
    
    Note: Email and phone are intentionally excluded to enforce platform-only communication.
    """
    class Meta:
        model = User
        fields = ['id', 'username', 'first_name', 'last_name', 'profile_picture']


class ProjectNestedSerializer(serializers.ModelSerializer):
    """
    Lightweight serializer for embedding project information in proposals.
    
    Provides essential project context when viewing a proposal without
    requiring a separate API call to fetch full project details.
    
    Fields:
        id (int): Project unique identifier
        title (str): Project title/name
        budget (Decimal): Client's set budget for the project
    """
    class Meta:
        model = Project
        fields = ['id', 'title', 'budget', 'description']


class ProposalSerializer(serializers.ModelSerializer):
    """
    Main serializer for Proposal model with platform-enforced communication.
    
    Business Rules:
    - bid_amount is read-only and auto-set to project.budget on creation
    - Freelancers cannot negotiate price (fixed-price model)
    - Contact info NEVER exposed - all communication via platform messaging
    - Protects platform revenue and user safety
    
    Fields:
    - project: returns full nested object {id, title, budget, description}
    """
    # Computed fields that require custom logic
    freelancer_details = serializers.SerializerMethodField(read_only=True)
    # Use nested serializer for the main 'project' field
    project = ProjectNestedSerializer(read_only=True)
    # project_details is now redundant but kept for backward compatibility if needed
    project_details = ProjectNestedSerializer(source='project', read_only=True)

    class Meta:
        model = Proposal
        fields = [
            'id', 
            'project',
            'freelancer',
            'bid_amount', 
            'cover_letter', 
            'status', 
            'created_at',
            'freelancer_details',
            'project_details',
            'thumbnail',
        ]
        
        # Fields that should never be modified by client requests
        read_only_fields = [
            'status',        # Only changeable via dedicated status update endpoint
            'freelancer',    # Set automatically from request.user
            'project',       # Set automatically from URL parameter
            'created_at',    # Auto-generated timestamp
            'bid_amount',    # Auto-populated from project.budget (fixed-price model)
        ]

    def get_freelancer_details(self, obj):
        """
        Return freelancer public profile information.
        
        Returns basic freelancer details (name, username) without exposing
        contact information. This enforces the platform's policy that all
        communication must happen through the internal messaging system.
        
        Args:
            obj (Proposal): The proposal instance being serialized
            
        Returns:
            dict: Serialized freelancer data (public profile only)
            
        Response Format:
            {
                "id": 123,
                "username": "john_dev",
                "first_name": "John",
                "last_name": "Doe"
            }
        
        Security & Business Rules:
            - Email and phone numbers are NEVER exposed via API
            - All communication must happen through platform messaging
            - This prevents circumventing platform fees/monitoring
            - Protects user privacy and platform revenue
        """
        # Import here to avoid circular dependency
        from User.Serializers import FreelancerDetailSerializer
        
        # Always return minimal public information
        # Email/phone never exposed to enforce platform-only communication
        return FreelancerDetailSerializer(obj.freelancer).data


class ProposalStatusUpdateSerializer(serializers.ModelSerializer):
    """
    Dedicated serializer for updating proposal status.
    
    This serializer is used exclusively for the proposal status update
    endpoint, ensuring that clients can only modify the status field
    and nothing else about the proposal.
    
    Fields:
        status (str): New proposal status (ACCEPTED or REJECTED)
        
    Validation:
        - Only ACCEPTED and REJECTED statuses are allowed
        - Additional business logic validation in the view layer
        
    Usage:
        Used in the PATCH /proposals/{id}/status/ endpoint
        Clients can accept or reject freelancer proposals
    """
    class Meta:
        model = Proposal
        fields = ['status']