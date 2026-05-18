from django.db import models
from django.conf import settings 
# Commented Typo changes suggested by Gemini


class Proposal(models.Model):
    # Core Fields
    title = models.CharField(max_length=200, default="Proposal") 
    thumbnail = models.ImageField(upload_to='proposal_thumbnails/', blank=True, null=True)
    bid_amount = models.DecimalField(max_digits=10, decimal_places=2)
    cover_letter = models.TextField()
    

    
    project = models.ForeignKey(
        'Project.Project', 
        on_delete=models.CASCADE,
        related_name='proposals' # Naming the reverse relationship
    )
    freelancer = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name='submitted_proposals' # Naming the reverse relationship 
    )
    
    # Proposal Status Choices
    class ProposalStatus(models.TextChoices):
        PENDING = 'PENDING', 'Pending' 
        REJECTED = 'REJECTED', 'Rejected'
        ACCEPTED = 'ACCEPTED', 'Accepted'
        
    status = models.CharField(
        max_length=20, 
        choices=ProposalStatus.choices,
        default=ProposalStatus.PENDING,
        help_text="The current status of this proposal.",
        db_index=True  # Index for filtering proposals by status
    )
    
    # Timestamps (Recommended) 
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)  # Index for sorting proposals by date
    
    def __str__(self):
        return f"Proposal for {self.project.title} by {self.freelancer.username}"

    class Meta:
        # Enforce that a freelancer can only submit one proposal per project
        unique_together = ('project', 'freelancer')
        indexes = [
            models.Index(fields=['project', 'status']),  # Viewing proposals for a specific project
            models.Index(fields=['freelancer', 'status']),  # Freelancer's proposal dashboard
        ]