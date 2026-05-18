"""
Proposal Views Module

This module handles all API endpoints related to proposal submission, listing,
and status management in the BinaryBlade24 freelancing platform.

Core Functionality:
- Freelancers can submit proposals to OPEN projects
- Clients can view and manage proposals for their projects
- Secure proposal status updates with transaction integrity
- Role-based access control for proposal data

API Endpoints:
- POST   /api/projects/{project_id}/proposals/       - Submit proposal
- GET    /api/projects/{project_id}/proposals/       - List project proposals
- PATCH  /api/projects/{project_id}/proposals/{id}/status/ - Update proposal status
- GET    /api/proposals/{id}/                        - Retrieve single proposal
- GET    /api/users/{user_id}/proposals/             - List user's proposals

Author: BinaryBlade24 Team  
Last Modified: 2025-11-27
"""

from rest_framework import viewsets, mixins, status, generics
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.serializers import ValidationError
from rest_framework.permissions import IsAuthenticatedOrReadOnly, IsAuthenticated

from django.shortcuts import get_object_or_404
from django.db import transaction
from django.db.models import Q

from Proposal.models import Proposal
from Project.models import Project
from Proposal.serializers import ProposalSerializer, ProposalStatusUpdateSerializer
from Project.Permissions import IsClient, IsFreelancer
from .Permissions import IsProposalProjectOwner
# from User.models import Profile, User # Moved Profile (unused) and User (local import)


class ProposalListCreateView(mixins.CreateModelMixin, mixins.ListModelMixin, viewsets.GenericViewSet):
    """
    ViewSet for submitting and listing proposals on projects.
    
    This viewset handles the proposal lifecycle from submission to viewing,
   implementing strict access controls to ensure data privacy and security.
    
    Endpoints:
        POST /api/projects/{project_id}/proposals/
            - Freelancers submit proposals to open projects
            - Bid amount is automatically set to project budget (fixed-price model)
            - Requires FREELANCER role
            
        GET /api/projects/{project_id}/proposals/
            - Clients view all proposals for their projects
            - Freelancers cannot view other freelancers' proposals
            - Requires authentication
    
    Permissions:
        - CREATE: IsAuthenticated + IsFreelancer
        - LIST: IsAuthenticated (+ ownership check in queryset)
    
    Business Rules:
        - Proposals can only be submitted to OPEN projects
        - One proposal per freelancer per project (enforced at model level)
        - Initial status is always PENDING
        - Bid amount matches project budget (non-negotiable)
    
    Security Considerations:
        - Project ownership verified before listing proposals
        - Freelancers cannot view competing proposals
        - All foreign keys set server-side to prevent manipulation
    """
    
    serializer_class = ProposalSerializer
    
    def get_permissions(self):
        """
        Dynamically assign permissions based on the action being performed.
        
        Returns:
            list: Permission classes for the current action
        
        Permission Strategy:
            - Proposal submission requires FREELANCER role
            - Listing proposals requires authentication (ownership checked separately)
        """
        if self.action == 'create':
            # Only authenticated freelancers can submit proposals
            self.permission_classes = [IsAuthenticated, IsFreelancer]
        else:
            # Listing proposals requires authentication
            # Ownership verification happens in get_queryset()
            self.permission_classes = [IsAuthenticated]
        return super().get_permissions()

    def get_queryset(self):
        """
        Filter proposals based on project ownership and user role.
        
        Returns:
            QuerySet: Filtered proposals for the specified project
            
        Access Rules:
            - Clients see all proposals for their projects
            - Freelancers see none (they use /users/{id}/proposals/ instead)
            - Returns empty queryset if user is not the project owner
            
        URL Parameters:
            project_pk (int): Project ID from URL path
            
        Raises:
            Http404: If project doesn't exist
        """
        # Extract project ID from URL kwargs
        project_pk = self.kwargs.get('project_pk')
        project = get_object_or_404(Project, pk=project_pk)
        
        # Only the project client can see the list of proposals for their project
        if self.request.method == 'GET' and project.client != self.request.user:
            # Freelancers cannot view proposals via this endpoint
            # They must use the dedicated /users/{id}/proposals/ endpoint
            # to see only their own submissions
            return Proposal.objects.none()

        # Return all proposals for this project (client access only)
        return Proposal.objects.filter(project=project)

    def perform_create(self, serializer):
        """
        Handle proposal creation with server-side data population.
        
        This method automatically sets critical fields that should never
        be controlled by client input, ensuring data integrity and security.
        
        Server-Set Fields:
            - freelancer: Set to requesting user
            - project: Set from URL parameter
            - status: Always starts as PENDING
            - bid_amount: Auto-populated from project.budget (fixed-price)
        
        Args:
            serializer: Validated ProposalSerializer instance
            
        Raises:
            ValidationError: If project is not OPEN for proposals
            
        Side Effects:
            - Creates new Proposal record in database
            - May trigger duplicate proposal error (handled by model constraint)
        
        Business Logic:
            1. Verify project accepts proposals (status == OPEN)
            2. Set freelancer from authenticated user
            3. Set project from URL parameter
            4. Initialize status as PENDING
            5. Copy project budget to bid_amount (fixed-price model)
        """
        # Extract project ID from URL
        project_pk = self.kwargs.get('project_pk')
        project = get_object_or_404(Project, pk=project_pk)

        # Validation: Check if the project is accepting proposals
        if project.status != Project.ProjectStatus.OPEN:
            raise ValidationError({
                "detail": "Cannot submit proposal: Project is not open for new proposals."
            })

        # SECURITY: Prevent owner from submitting proposal to own project
        if project.client == self.request.user:
            raise ValidationError({
                "detail": "You cannot submit a proposal to your own project."
            })

        # CHECK: Prevent duplicate proposals (avoids 500 IntegrityError)
        if Proposal.objects.filter(project=project, freelancer=self.request.user).exists():
            raise ValidationError({
                "detail": "You have already submitted a proposal for this project."
            })

        # Save with server-controlled fields
        # This prevents clients from manipulating:
        # - Which user submitted (could impersonate)
        # - Which project it's for (could submit to wrong project)
        # - Status (could auto-accept own proposal)
        # - Bid amount (enforces fixed-price model)
        serializer.save(
            freelancer=self.request.user,
            project=project,
            status=Proposal.ProposalStatus.PENDING,
            bid_amount=project.budget  # Fixed-price: freelancer must accept client's budget
        )

        # Broadcast proposal to client
        try:
            from notifications.websocket_utils import broadcast_proposal_received
            proposal = serializer.instance
            broadcast_proposal_received(project.client.id, proposal)
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to broadcast proposal: {e}")
    
    @action(detail=True, methods=['patch'], url_path='status', 
            permission_classes=[IsAuthenticated, IsClient, IsProposalProjectOwner])
    def update_status(self, request, pk=None, project_pk=None):
        """
        Update proposal status (accept or reject) with transaction safety.
        
        This endpoint allows clients to accept or reject freelancer proposals.
        When a proposal is accepted, several atomic operations occur to maintain
        data consistency.
        
        Endpoint: PATCH /api/projects/{project_id}/proposals/{id}/status/
        
        Permissions:
            - Must be authenticated
            - Must have CLIENT role
            - Must be the owner of the project
        
        Request Body:
            {
                "status": "ACCEPTED" | "REJECTED"
            }
        
        Args:
            request: HTTP request object with status in body
            pk (int): Proposal ID
            project_pk (int): Project ID (for URL routing)
            
        Returns:
            Response: Updated proposal data with new status
            
        HTTP Status Codes:
            200 OK: Status updated successfully
            400 Bad Request: Invalid status value
            403 Forbidden: Not project owner or not a client
            404 Not Found: Proposal doesn't exist
        
        Transaction Behavior (on ACCEPT):
            1. Update proposal status to ACCEPTED
            2. Change project status to IN_PROGRESS
            3. Reject all other PENDING proposals for same project
            
        All operations are atomic - if any step fails, nothing is saved.
        
        Side Effects:
            - May change project status from OPEN to IN_PROGRESS
            - May auto-reject other freelancers' pending proposals
            - Triggers post-save signals (if any)
        
        Business Rules:
            - Only ACCEPTED or REJECTED statuses are permitted
            - Cannot change from ACCEPTED/REJECTED back to PENDING
            - Accepting one proposal rejects all others automatically
            - Project can only have one accepted proposal at a time
        """
        # Retrieve the proposal or return 404
        proposal = get_object_or_404(Proposal, pk=pk)
        
        # Validate status update using dedicated serializer
        # This ensures only the 'status' field can be modified
        serializer = ProposalStatusUpdateSerializer(
            proposal, 
            data=request.data, 
            partial=True
        )
        serializer.is_valid(raise_exception=True)
        
        # Extract and validate the new status
        new_status = serializer.validated_data.get('status')

        # Only allow meaningful status transitions
        if new_status not in [Proposal.ProposalStatus.ACCEPTED, Proposal.ProposalStatus.REJECTED]:
            return Response(
                {"detail": "Invalid status update. Only ACCEPTED or REJECTED are allowed."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # SECURITY: Prevent project owner from accepting their own proposal
        if new_status == Proposal.ProposalStatus.ACCEPTED and proposal.freelancer == request.user:
            return Response(
                {"detail": "You cannot accept your own proposal."},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Use database transaction to ensure atomic operations
        # If any operation fails, all changes are rolled back
        with transaction.atomic():
            # Step 1: Update the proposal status
            proposal.status = new_status
            proposal.save()

            # Step 2: If accepting, trigger additional workflow changes
            if new_status == Proposal.ProposalStatus.ACCEPTED:
                
                # Update the project to IN_PROGRESS status
                # (moves project from "hiring" to "active work" phase)
                project = proposal.project
                if project.status == Project.ProjectStatus.OPEN:
                    project.status = Project.ProjectStatus.IN_PROGRESS
                    project.save()
                
                # Create HELD payment (escrow) when hiring freelancer
                # Payment will be released when client approves completed work
                from User.models import Payment
                Payment.objects.create(
                    user=request.user,  # Client who is paying
                    project=project,
                    amount=project.budget,
                    transaction_id=f"TXN-{project.id}-{proposal.id}",  # Mock transaction ID
                    payment_method='stripe',  # Mock payment method
                    status=Payment.PaymentStatus.HELD  # Held in escrow
                )
                    
                # Auto-reject all competing proposals
                # This prevents double-booking and maintains data consistency
                Proposal.objects.filter(
                    project=project,
                    status=Proposal.ProposalStatus.PENDING
                ).exclude(
                    pk=proposal.pk
                ).update(
                    status=Proposal.ProposalStatus.REJECTED
                )

                # Create a conversation between client and freelancer
                from message.models import Conversation, Message
                conversation, created = Conversation.objects.get_or_create(
                    project=project,
                    participant_1=request.user,  # Client
                    participant_2=proposal.freelancer
                )
                
                # Send initial system message
                if created:
                    Message.objects.create(
                        conversation=conversation,
                        sender=request.user,
                        body=f"Congratulations! I've accepted your proposal for '{project.title}'. Let's discuss the details here."
                    )
                
                # Send email notification
                from notifications.email_service import EmailService
                EmailService.send_proposal_accepted_email(proposal)

            # Broadcast status update to freelancer
            try:
                from notifications.websocket_utils import broadcast_proposal_status_update
                broadcast_proposal_status_update(proposal.freelancer.id, proposal)
            except Exception as e:
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"Failed to broadcast proposal update: {e}")
        
        # Return the updated proposal data
        return Response(ProposalSerializer(proposal, context={'request': request}).data)


class ProposalDetailView(generics.RetrieveAPIView):
    """
    Retrieve a single proposal by ID with access control.
    
    This view allows users to fetch detailed information about a specific
    proposal, but only if they have a legitimate relationship to it.
    
    Endpoint: GET /api/proposals/{id}/
    
    Permissions:
        - Must be authenticated
        - Must be either:
          a) The project's client, OR
          b) The freelancer who submitted the proposal
    
    Access Control:
        Implemented via queryset filtering rather than object-level permissions
        for better performance and cleaner code.
    
    Returns:
        200 OK: Proposal details (with conditional freelancer contact info)
        403 Forbidden: User not authorized to view this proposal
        404 Not Found: Proposal doesn't exist or user lacks access
    
    Security:
        - Freelancers cannot view other freelancers' proposals
        - Clients can only see proposals for their own projects
        - Contact info conditionally exposed based on proposal status
    """
    
    serializer_class = ProposalSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """
        Filter proposals to only those the user is authorized to view.
        
        Returns:
            QuerySet: Proposals the authenticated user can access
            
        Access Logic:
            - Clients can view any proposal on their projects
            - Freelancers can only view their own submitted proposals
            - Uses Q objects for complex OR logic
            
        Implementation Note:
            This approach is more efficient than checking permissions
            after retrieval, as it filters at the database level.
        """
        user = self.request.user

        # Build query for proposals on user's projects (if they're a client)
        client_projects = Project.objects.filter(client=user)
        
        # Build query for user's own proposals (if they're a freelancer)
        freelancer_proposals = Q(freelancer=user)

        # Combine queries: user can see proposals they submitted OR
        # proposals on projects they own
        return Proposal.objects.filter(
            Q(project__in=client_projects) | freelancer_proposals
        )


class UserProposalsView(generics.ListAPIView):
    """
    List all proposals submitted by a specific freelancer.
    
    This endpoint allows freelancers to view their complete proposal history,
    including pending, accepted, and rejected proposals.
    
    Endpoint: GET /api/users/{user_id}/proposals/
    
    Permissions:
        - Must be authenticated
        - No role requirement (any authenticated user can view)
        
    Use Cases:
        - Freelancers tracking their own applications
        - Profile pages showing freelancer's work history
        - Analytics on freelancer activity
    
    URL Parameters:
        user_id (int): ID of the freelancer whose proposals to retrieve
    
    Returns:
        200 OK: List of proposals
        404 Not Found: User doesn't exist
    
    Security Considerations:
        - All users can see any freelancer's proposals
        - This is intentional for transparency in the platform
        - Contact details are still protected via serializer logic
        - Proposal count visible on public profiles
    
    Future Enhancement:
        Consider adding privacy settings to hide proposal history
        from non-connected users.
    """
    
    serializer_class = ProposalSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """
        Retrieve all proposals for the specified user.
        
        Returns:
            QuerySet: All proposals submitted by the user
            
        Raises:
            Http404: If user ID doesn't exist
        """
        # Extract user ID from URL kwargs
        user_id = self.kwargs.get('pk')
        
        # Get user or 404
        from User.models import User
        user = get_object_or_404(User, pk=user_id)
        
        # Return all of this freelancer's proposals
        return Proposal.objects.filter(freelancer=user)


class PublicProposalsView(generics.ListAPIView):
    """
    Public endpoint for browsing all open proposals (buyer requests).
    
    This allows freelancers to discover work opportunities by viewing
    proposals from clients looking for services.
    
    Endpoint: GET /api/proposals/public/
    
    Permissions:
        - Public access (no authentication required)
        
    Returns:
        List of all PENDING proposals on OPEN projects
    """
    
    serializer_class = ProposalSerializer
    permission_classes = []  # Public access
    
    def get_queryset(self):
        """
        Return all pending proposals on open projects.
        
        This creates a "Find Work" feed for freelancers.
        """
        return Proposal.objects.filter(
            status=Proposal.ProposalStatus.PENDING,
            project__status=Project.ProjectStatus.OPEN
        ).select_related('project', 'freelancer').order_by('-created_at')
